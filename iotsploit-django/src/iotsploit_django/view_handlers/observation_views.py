"""Read access to scan observations.

Only the current state is exposed here: the latest complete, succeeded scan per
(component, source, scope). History, diffs and scan-run listings are separate
questions and get their own endpoints when something needs them.
"""

import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def get_current_observations(request):
    """
    GET ?target_id=<id>
    Current observed facts for one target.

    Each record carries its own provenance -- which tool, which scope, which
    scan, when -- because two tools may report on the same subject and the
    caller has to be able to tell them apart.
    """
    target_id = request.GET.get('target_id')
    if not target_id:
        return JsonResponse({'error': 'target_id is required'}, status=400)

    try:
        from iotsploit_django.adapters.django.observation_repository import ObservationRepository

        records = ObservationRepository().current(target_id)
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
