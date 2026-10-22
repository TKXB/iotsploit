"""Read and write access to scan observations.

Only the current state is exposed for reading: the latest complete, succeeded
scan per (component, source, scope). History, diffs and scan-run listings are
separate questions and get their own endpoints when something needs them.

The write path exists for callers that observed something themselves rather
than by running a plugin -- an agent that probed a port, a tool run on the
bench. Those are real measurements and deserve to be durable. What they may not
do is *look* like a plugin's measurement, so the source is assigned here and
not by the caller. See ``AGENT_SOURCE_PREFIX``.
"""

import json
import logging
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from iotsploit_core.domain.observation import Fact

logger = logging.getLogger(__name__)

# Every source recorded over HTTP lives under this prefix. The caller names the
# label after it and nothing more: the namespace is not negotiable, so a fact
# written this way can never claim to have come from `can_sniff` or
# `nmap_scan`. Plugins get their source stamped by ExploitManager from the
# plugin name, which is the same property arrived at from the other side.
#
# This API has no authentication, so the label is a claim about *which* agent
# and not proof of one. The prefix is the part that stays true regardless, and
# it is the part the distinction rests on: measured by a tool, or reported by
# something that was asked to look.
AGENT_SOURCE_PREFIX = "agent:"

# `source` ends up in a log line, a URL query and a scope comparison, so it is
# held to a charset that survives all three unchanged.
_UNSAFE_LABEL = re.compile(r"[^a-z0-9._-]+")


def agent_source(label: str) -> str:
    """The source string for a caller-supplied agent label.

    Sanitised rather than rejected: the label is cosmetic, and refusing a write
    because an agent called itself "Claude Code" would lose a real observation
    over punctuation. The prefix is what carries meaning and it is added here.
    """
    cleaned = _UNSAFE_LABEL.sub("-", (label or "").strip().lower()).strip("-")
    return f"{AGENT_SOURCE_PREFIX}{cleaned or 'unknown'}"


def get_current_observations(request):
    """
    GET ?target_id=<id>[&component_id=][&source=][&protocol=][&subject_kind=]
    Current observed facts for one target.

    Each record carries its own provenance -- which tool, which scope, which
    scan, when -- because two tools may report on the same subject and the
    caller has to be able to tell them apart.

    ``component_id`` and ``source`` narrow the query itself: they are scan-run
    columns. ``protocol`` and ``subject_kind`` describe individual facts, so
    they are applied to the records afterwards -- the same answer, but it does
    not pretend to save the database any work.
    """
    target_id = request.GET.get('target_id')
    if not target_id:
        return JsonResponse({'error': 'target_id is required'}, status=400)

    protocol = request.GET.get('protocol')
    subject_kind = request.GET.get('subject_kind')

    try:
        from iotsploit_django.adapters.django.observation_repository import ObservationRepository

        records = ObservationRepository().current(
            target_id,
            component_id=request.GET.get('component_id'),
            source=request.GET.get('source'),
        )
        if protocol:
            records = [r for r in records if r.protocol == protocol]
        if subject_kind:
            records = [r for r in records if r.subject_kind == subject_kind]
    except Exception as e:
        logger.error(f"Error reading observations for {target_id}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'status': 'success',
        'target_id': target_id,
        'observations': [
            {
                'component_id': record.component_id,
                'source': record.source,
                'scope_key': record.scope_key,
                'protocol': record.protocol,
                'subject_kind': record.subject_kind,
                'subject_id': record.subject_id,
                'observed_property': record.observed_property,
                'value': record.value,
                'display_key': record.display_key,
                'scan_id': record.scan_id,
                'observed_at': record.observed_at.isoformat() if record.observed_at else None,
            }
            for record in records
        ],
    })


@csrf_exempt
def record_observations(request):
    """
    POST
    Record what the caller observed on one target, as a single scan.

    Expected JSON body:
    {
        "target_id": "zxd",
        "agent": "claude",              // label; stored as "agent:claude"
        "scope_key": "tcp:22,80,443",   // what was actually examined
        "component_id": "c_gateway",    // optional
        "is_complete": true,            // optional, defaults true
        "facts": [
            {"protocol": "tcp", "subject_kind": "port", "subject_id": "22",
             "observed_property": "open", "value": {"banner": "OpenSSH 8.9"}}
        ]
    }

    ``scope_key`` is required because ``is_complete`` is a claim *about it*: it
    says these facts are the whole population of that scope, which is what lets
    a later scan record something as having disappeared. Name what was really
    looked at ("tcp:22,80,443", not "tcp") and the claim stays true.

    Completeness here is safe in a way it would not be if the caller chose its
    own source. ``source`` is one of the repository's COMPARABLE_SCOPE_FIELDS,
    so a scan under ``agent:x`` is never comparable with one under ``can_sniff``
    -- an agent's snapshot can only ever replace its own previous snapshot of
    the same scope, and cannot make a plugin's facts vanish.

    An empty ``facts`` list is valid and meaningful: a successful scan that
    found nothing is how "this is not exposed" gets recorded.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({'error': 'Body must be a JSON object'}, status=400)

    if 'source' in data:
        # Refused rather than ignored. A caller that believes it chose the
        # source would otherwise be told its facts were recorded, under a name
        # it never sent and cannot see -- the same failure as accepting a field
        # and discarding it.
        return JsonResponse({
            'error': "source is assigned by the server, not the caller; send 'agent' "
                     f"instead and it is recorded as '{AGENT_SOURCE_PREFIX}<agent>'",
        }, status=400)

    target_id = data.get('target_id')
    if not target_id:
        return JsonResponse({'error': 'target_id is required'}, status=400)

    scope_key = data.get('scope_key')
    if not scope_key:
        return JsonResponse({
            'error': 'scope_key is required: it names the population examined, and '
                     'is_complete is a claim about that population',
        }, status=400)

    facts_payload = data.get('facts', [])
    if not isinstance(facts_payload, list):
        return JsonResponse({'error': 'facts must be a list'}, status=400)

    # Validated before the scan row is opened, so a malformed payload leaves no
    # trace at all rather than a scan that was started and never finished.
    facts = []
    identities = set()
    for index, item in enumerate(facts_payload):
        if not isinstance(item, dict):
            return JsonResponse({'error': f'facts[{index}] must be an object'}, status=400)
        try:
            fact = Fact(**item)
        except ValidationError as exc:
            return JsonResponse({'error': f'facts[{index}] is invalid: {exc}'}, status=400)
        if fact.identity in identities:
            # The database enforces this too, but as an integrity error after
            # the scan has been opened. Caught here it names the offender.
            return JsonResponse({
                'error': f"facts[{index}] repeats '{fact.display_key}'; one scan may state each "
                         'protocol/subject/property once',
            }, status=400)
        identities.add(fact.identity)
        facts.append(fact)

    source = agent_source(data.get('agent'))
    is_complete = bool(data.get('is_complete', True))

    try:
        from iotsploit_django.adapters.django.observation_repository import ObservationRepository

        repository = ObservationRepository()
        scan_id = repository.start_scan(
            target_id=target_id,
            source=source,
            scope_key=scope_key,
            component_id=data.get('component_id'),
        )
    except Exception as e:
        logger.error(f"Error starting scan for {target_id}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    try:
        recorded = repository.complete_scan(scan_id, facts, is_complete=is_complete)
    except Exception as e:
        # The scan row already exists. Left alone it would stay RUNNING for
        # ever, which reads as a scan still in flight rather than one that
        # broke.
        repository.fail_scan(scan_id, str(e))
        logger.error(f"Error recording observations for {target_id}: {str(e)}")
        return JsonResponse({'error': str(e), 'scan_id': scan_id}, status=500)

    return JsonResponse({
        'status': 'success',
        'target_id': target_id,
        'scan_id': scan_id,
        'source': source,
        'scope_key': scope_key,
        'is_complete': is_complete,
        'facts_recorded': recorded,
    })
