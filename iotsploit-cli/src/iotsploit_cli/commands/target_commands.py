#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from cmd2.table_creator import Column, SimpleTable
from .base_commands import BaseCommands
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)

# Fields rendered in their own column, so the detail line does not repeat them.
_COMPONENT_HEADER_FIELDS = ('component_id', 'name', 'type', 'status')
_BUS_HEADER_FIELDS = ('bus_id', 'name', 'type')

_STATUS_COLORS = {
    'active': ansi.Fg.GREEN,
    'online': ansi.Fg.GREEN,
    'inactive': ansi.Fg.LIGHT_GRAY,
    'offline': ansi.Fg.LIGHT_GRAY,
    'error': ansi.Fg.RED,
}


def _style_status(status):
    return ansi.style(status or 'unknown', fg=_STATUS_COLORS.get((status or '').lower(), ansi.Fg.YELLOW))


def _summarize(value):
    """A value small enough to sit in a table cell.

    A CAN facet holds a whole network. Printed as a dict it came to four
    kilobytes of Python syntax that the column then cut off after sixty
    characters, which told an operator nothing at all. Lists are counted
    rather than printed; their contents belong in the facet editor.
    """
    if isinstance(value, dict):
        return '{' + ', '.join(f"{k}={_summarize(v)}" for k, v in value.items()) + '}'
    if isinstance(value, list):
        return f"{len(value)} item{'' if len(value) == 1 else 's'}"
    return str(value)


def _flatten(mapping, skip=()):
    """Render a dict as 'k=v' pairs, skipping keys shown elsewhere."""
    if not isinstance(mapping, dict):
        return str(mapping) if mapping else ''
    return ', '.join(
        f"{k}={_summarize(v)}" for k, v in mapping.items() if k not in skip and v not in (None, '', {}, [])
    )


def _detail_of(entry, header_fields):
    """Everything about a component or bus that is not already a column.

    Facets are left out: they have their own section, where there is room to
    say which component each one belongs to.
    """
    extras = {k: v for k, v in entry.items() if k not in header_fields and k not in ('properties', 'facets')}
    parts = [_flatten(extras), _flatten(entry.get('properties') or {})]
    return ', '.join(p for p in parts if p)


def _facet_rows(components):
    """One row per configured facet: which component, which key, what is set."""
    rows = []
    for component in components:
        facets = component.get('facets') or {}
        label = component.get('name') or component.get('component_id') or '?'
        for key in sorted(facets):
            rows.append([label, key, _flatten(facets[key])])
    return rows


def _compact(value):
    """Render an observation value without JSON noise.

    Null is spelled the way it was stored rather than as Python's None: an
    absent UDS negative-response code is the difference between "the ECU
    answered" and "it refused", so it has to read unambiguously.
    """
    if isinstance(value, dict):
        return ', '.join(f"{k}={_compact(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ', '.join(_compact(v) for v in value)
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _fit(columns, rows, minimums):
    """Size each column to its widest cell, floored at the header width."""
    for index, column in enumerate(columns):
        widest = max((len(str(row[index])) for row in rows), default=0)
        column.width = max(widest, len(column.header), minimums[index])


class TargetCommands(BaseCommands):
    """Target-related commands for the SAT Shell"""

    @cmd2.with_category('Target Commands')
    def do_list_targets(self, arg):
        """List targets stored in the database.

        target list             summary table of every target
        target list <id|name>   full detail for one target
        target list all         full detail for every target
        """
        try:
            targets = self.target_manager.get_all_targets()

            if not targets:
                self.poutput(ansi.style("No targets found in the database.", fg=ansi.Fg.YELLOW))
                return

            current = self.target_manager.get_current_target()
            current_id = getattr(current, 'target_id', None)
            wanted = (arg or '').strip()

            if not wanted:
                self._print_target_table(targets, current_id)
                self.poutput(
                    ansi.style(
                        "\nUse 'target list <id>' for components, facets and topology.", fg=ansi.Fg.LIGHT_GRAY
                    )
                )
                return

            if wanted.lower() == 'all':
                selected = targets
            else:
                selected = [t for t in targets if wanted in (t.get('target_id'), t.get('name'))]
                if not selected:
                    logger.error(
                        ansi.style(f"Target '{wanted}' not found. Use 'target list' to view targets.", fg=ansi.Fg.RED)
                    )
                    return

            for target in selected:
                self._print_target_detail(target, current_id)

        except Exception as e:
            logger.error(ansi.style(f"Error listing targets: {str(e)}", fg=ansi.Fg.RED))

    do_lst = do_list_targets

    @cmd2.with_category('Target Commands')
    def do_target_observations(self, arg):
        """Show what scans have discovered about a target.

        target observations         facts for the active target
        target observations <id>    facts for a named target

        Shows the current view: the latest successful complete scan for each
        tool and scope. Failed and partial scans are excluded, so nothing here
        is an artifact of a scan that did not finish.
        """
        try:
            wanted = (arg or '').strip()
            if wanted:
                target = next(
                    (t for t in self.target_manager.get_all_targets()
                     if wanted in (t.get('target_id'), t.get('name'))),
                    None,
                )
                if target is None:
                    logger.error(
                        ansi.style(f"Target '{wanted}' not found. Use 'target list' to view targets.", fg=ansi.Fg.RED)
                    )
                    return
                target_id, target_name = target['target_id'], target.get('name')
            else:
                current = self.target_manager.get_current_target()
                if current is None:
                    logger.error(
                        ansi.style("No target selected. Use 'target select' or pass a target id.", fg=ansi.Fg.RED)
                    )
                    return
                target_id, target_name = current.target_id, current.name

            records = self._observation_repository().current(target_id)
            self._print_observations(target_id, target_name, records)

        except Exception as e:
            logger.error(ansi.style(f"Error reading observations: {str(e)}", fg=ansi.Fg.RED))

    do_obs = do_target_observations

    @staticmethod
    def _observation_repository():
        # Imported lazily: the CLI starts without touching the observation
        # database unless this command is actually used.
        from iotsploit_django.adapters.django.observation_repository import ObservationRepository

        return ObservationRepository()

    # ---------------- rendering helpers ----------------

    def _print_observations(self, target_id, target_name, records):
        header = ansi.style(f"\nObservations — {target_name or target_id}", fg=ansi.Fg.CYAN, bold=True)
        self.poutput(header + ansi.style(f"  [{target_id}]", fg=ansi.Fg.LIGHT_GRAY))

        if not records:
            self.poutput(ansi.style("  No scan has recorded anything for this target yet.", fg=ansi.Fg.YELLOW))
            return

        sources = sorted({r.source for r in records})
        self.poutput(
            ansi.style(f"  {len(records)} current facts from {len(sources)} tools: {', '.join(sources)}",
                       fg=ansi.Fg.LIGHT_GRAY)
        )

        ordered = sorted(
            records,
            key=lambda r: (r.component_id or '', r.source, r.protocol, r.subject_kind, r.subject_id or ''),
        )
        columns = [Column('COMPONENT'), Column('SOURCE'), Column('FACT'), Column('VALUE'), Column('OBSERVED')]
        rows = [
            [
                r.component_id or '(target)',
                r.source,
                r.display_key,
                _compact(r.value),
                r.observed_at.strftime('%Y-%m-%d %H:%M') if r.observed_at else '',
            ]
            for r in ordered
        ]
        _fit(columns, rows, minimums=[9, 6, 10, 5, 16])
        columns[3].width = min(columns[3].width, 44)

        self.poutput('')
        self.poutput(SimpleTable(columns).generate_table(rows, row_spacing=0))

    def _print_target_table(self, targets, current_id):
        columns = [
            Column(''), Column('ID'), Column('Name'), Column('Type'),
            Column('Status'), Column('IP Address'), Column('Location'), Column('Comp'), Column('Bus'),
        ]
        rows = []
        for target in targets:
            components = target.get('components') or []
            # Interfaces were folded into components and the column went with
            # them; buses are the second list a target has now.
            buses = target.get('buses') or []
            rows.append([
                '*' if target.get('target_id') == current_id else '',
                target.get('target_id') or '',
                target.get('name') or '',
                target.get('type') or '',
                target.get('status') or '',
                target.get('ip_address') or '-',
                target.get('location') or '-',
                str(len(components)),
                str(len(buses)),
            ])

        _fit(columns, rows, minimums=[1, 8, 8, 6, 6, 10, 8, 4, 4])
        # Colour after sizing: ANSI escapes would otherwise distort the widths.
        for row in rows:
            row[0] = ansi.style(row[0], fg=ansi.Fg.GREEN, bold=True)
            row[4] = _style_status(row[4])

        self.poutput(ansi.style(f"\nTargets ({len(targets)})", fg=ansi.Fg.CYAN, bold=True))
        self.poutput(SimpleTable(columns).generate_table(rows, row_spacing=0))

    def _print_target_detail(self, target, current_id):
        is_current = target.get('target_id') == current_id
        marker = ansi.style('* ', fg=ansi.Fg.GREEN, bold=True) if is_current else '  '

        self.poutput('')
        self.poutput(
            marker
            + ansi.style(target.get('name') or '(unnamed)', fg=ansi.Fg.CYAN, bold=True)
            + ansi.style(f"  [{target.get('target_id')}]", fg=ansi.Fg.LIGHT_GRAY)
        )

        summary = [
            f"type {target.get('type') or '-'}",
            f"status {_style_status(target.get('status'))}",
            f"ip {target.get('ip_address') or '-'}",
            f"location {target.get('location') or '-'}",
        ]
        self.poutput('    ' + ansi.style(' | ', fg=ansi.Fg.LIGHT_GRAY).join(summary))

        updated = target.get('updated_at')
        if updated:
            self.poutput(ansi.style(f"    updated {updated}", fg=ansi.Fg.LIGHT_GRAY))

        properties = target.get('properties') or {}
        if properties:
            self.poutput(ansi.style("\n    Properties", fg=ansi.Fg.CYAN))
            width = max(len(str(k)) for k in properties)
            for key, value in properties.items():
                self.poutput(f"      {str(key):<{width}}  {value}")

        components = target.get('components') or []
        self._print_entries(components, 'Components', 'component_id', _COMPONENT_HEADER_FIELDS)
        # Configuration, then the wiring it refers to. All three are printed
        # only when there is something to print: most targets carry no
        # topology, and three "none" lines apiece would bury the components.
        self._print_facets(components)
        self._print_buses(target.get('buses') or [])
        self._print_links(target.get('edges') or [])

    def _print_entries(self, entries, title, id_field, header_fields):
        self.poutput(ansi.style(f"\n    {title} ({len(entries)})", fg=ansi.Fg.CYAN))
        if not entries:
            self.poutput(ansi.style("      none", fg=ansi.Fg.LIGHT_GRAY))
            return

        columns = [Column('NAME'), Column('TYPE'), Column('STATUS'), Column('ID'), Column('DETAIL')]
        rows = [
            [
                entry.get('name') or '',
                entry.get('type') or '',
                entry.get('status') or '',
                entry.get(id_field) or '',
                _detail_of(entry, header_fields),
            ]
            for entry in entries
        ]
        _fit(columns, rows, minimums=[6, 8, 6, 8, 10])
        for row in rows:
            row[2] = _style_status(row[2])
        self._print_table(columns, rows)

    def _print_facets(self, components):
        """Typed protocol configuration, per component.

        Worth its own section rather than a column: a facet is what a driver
        actually reads, so "which ECU is on which address" and "which node
        speaks which frames" are the questions this listing exists to answer.
        """
        rows = _facet_rows(components)
        if not rows:
            return

        self.poutput(ansi.style(f"\n    Facets ({len(rows)})", fg=ansi.Fg.CYAN))
        columns = [Column('COMPONENT'), Column('FACET'), Column('CONFIGURATION')]
        _fit(columns, rows, minimums=[9, 5, 13])
        self._print_table(columns, rows, cap=72)

    def _print_buses(self, buses):
        if not buses:
            return

        self.poutput(ansi.style(f"\n    Buses ({len(buses)})", fg=ansi.Fg.CYAN))
        columns = [Column('NAME'), Column('TYPE'), Column('ID'), Column('DETAIL')]
        rows = [
            [bus.get('name') or '', bus.get('type') or '', bus.get('bus_id') or '', _detail_of(bus, _BUS_HEADER_FIELDS)]
            for bus in buses
        ]
        _fit(columns, rows, minimums=[6, 6, 8, 10])
        self._print_table(columns, rows)

    def _print_links(self, edges):
        """The topology, as the edges that were validated on save.

        Endpoints are printed as ids rather than names because that is what an
        edge stores, and what a mismatch would look like if one ever appeared.
        """
        if not edges:
            return

        self.poutput(ansi.style(f"\n    Edges ({len(edges)})", fg=ansi.Fg.CYAN))
        width = max(len(str(edge.get('source') or '')) for edge in edges)
        # The relation is padded too, so the endpoints line up in a column and
        # a target pointing somewhere unexpected is visible at a glance.
        relation_width = max(len(str(edge.get('relation') or '?')) for edge in edges)
        for edge in edges:
            source = str(edge.get('source') or '')
            relation = f"--{edge.get('relation') or '?'}->"
            self.poutput(f"      {source:<{width}}  {relation:<{relation_width + 4}}  {edge.get('target') or ''}")

    def _print_table(self, columns, rows, cap=60):
        """Print an indented table, keeping the last column on screen."""
        columns[-1].width = min(columns[-1].width, cap)
        for line in SimpleTable(columns).generate_table(rows, row_spacing=0).splitlines():
            self.poutput('      ' + line)

    @cmd2.with_category('Target Commands')
    def do_target_select(self, arg):
        'Select a target from available targets'
        try:
            targets = self.target_manager.get_all_targets()
            
            if not targets:
                logger.info(ansi.style("No targets found in the database.", fg=ansi.Fg.YELLOW))
                return

            requested_target = arg.strip() if arg else None

            # Create list of target choices for display
            # Show all targets with their type, and IP if available
            target_choices = []
            for t in targets:
                ip_part = f" - {t['ip_address']}" if t.get('ip_address') else ""
                target_choices.append(f"{t['name']} ({t['type']}){ip_part}")
            
            if requested_target:
                selected_index = next(
                    (
                        index
                        for index, target in enumerate(targets)
                        if requested_target in (target.get('name'), target.get('target_id'))
                    ),
                    None,
                )
                if selected_index is None:
                    logger.error(
                        ansi.style(
                            f"Target '{requested_target}' not found. Use 'target list' to view targets.",
                            fg=ansi.Fg.RED,
                        )
                    )
                    return
            else:
                selected_choice = Input_Mgr.Instance().single_choice(
                    "Select target for operation:",
                    target_choices
                )
                selected_index = target_choices.index(selected_choice)
            
            # Convert the selected target dictionary to a Vehicle instance using create_target_instance
            selected_target_dict = targets[selected_index]
            selected_target = self.target_manager.create_target_instance(selected_target_dict)
            
            # Set the selected target as current
            self.target_manager.set_current_target(selected_target)
            
            logger.info(ansi.style(f"Selected target: {selected_target.name}", fg=ansi.Fg.GREEN))

        except Exception as e:
            logger.error(ansi.style(f"Error selecting target: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Target Commands')
    def do_edit_target(self, arg):
        'Edit an existing target in the database'
        try:
            # Get all targets
            targets = self.target_manager.get_all_targets()
            if not targets:
                logger.warning(ansi.style("No targets available to edit.", fg=ansi.Fg.YELLOW))
                return

            requested_target = arg.strip() if arg else None
            if requested_target:
                target = next(
                    (
                        item for item in targets
                        if requested_target in (item.get('name'), item.get('target_id'))
                    ),
                    None,
                )
                if target is None:
                    logger.error(
                        ansi.style(
                            f"Target '{requested_target}' not found. Use 'target list' to view targets.",
                            fg=ansi.Fg.RED,
                        )
                    )
                    return
            else:
                target_choices = [f"{t['name']} ({t['target_id']})" for t in targets]
                selected = Input_Mgr.Instance().single_choice(
                    "Select target to edit",
                    target_choices
                )
                target_id = selected.split('(')[-1].split(')')[0]
                target = next(t for t in targets if t['target_id'] == target_id)
            
            # Fields that can be edited
            editable_fields = {
                'name': str,
                'status': str,
                'ip_address': str,
                'location': str
            }
            
            # Let user select which field to edit
            field_choices = list(editable_fields.keys()) + ['properties']
            field = Input_Mgr.Instance().single_choice(
                "Select field to edit",
                field_choices
            )
            
            if field == 'properties':
                # Handle properties editing
                print("\nCurrent properties:")
                for key, value in target['properties'].items():
                    print(f"{key}: {value}")
                
                # Let user choose to add/edit/delete property
                action = Input_Mgr.Instance().single_choice(
                    "Select action",
                    ['Add property', 'Edit property', 'Delete property']
                )
                
                if action == 'Add property':
                    key = Input_Mgr.Instance().string_input("Enter property name")
                    value = Input_Mgr.Instance().string_input("Enter property value")
                    target['properties'][key] = value
                
                elif action == 'Edit property':
                    if not target['properties']:
                        logger.warning(ansi.style("No properties to edit.", fg=ansi.Fg.YELLOW))
                        return
                    prop_key = Input_Mgr.Instance().single_choice(
                        "Select property to edit",
                        list(target['properties'].keys())
                    )
                    new_value = Input_Mgr.Instance().string_input(
                        f"Enter new value for {prop_key}"
                    )
                    target['properties'][prop_key] = new_value
                
                elif action == 'Delete property':
                    if not target['properties']:
                        logger.warning(ansi.style("No properties to delete.", fg=ansi.Fg.YELLOW))
                        return
                    prop_key = Input_Mgr.Instance().single_choice(
                        "Select property to delete",
                        list(target['properties'].keys())
                    )
                    del target['properties'][prop_key]
            
            else:
                # Handle regular field editing
                new_value = Input_Mgr.Instance().string_input(
                    f"Enter new value for {field}"
                )
                target[field] = new_value
            
            # Update the target in the database
            success = self.target_manager.update_target(target)
            
            if success:
                logger.info(ansi.style(f"Successfully updated target {target_id}", fg=ansi.Fg.GREEN))
            else:
                logger.error(ansi.style(f"Failed to update target {target_id}", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error editing target: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    do_et = do_edit_target

    @cmd2.with_category('Target Commands')
    def do_target_import(self, arg):
        'Import targets from JSON file (optional, only when needed)'
        try:
            if not arg:
                json_file = Input_Mgr.Instance().string_input(
                    "Enter JSON file path (default: conf/target.json)"
                ) or "conf/target.json"
            else:
                json_file = arg.strip()
            
            # Check if file exists
            import os
            if not os.path.exists(json_file):
                logger.error(ansi.style(f"File not found: {json_file}", fg=ansi.Fg.RED))
                return
            
            # Check existing targets
            existing_targets = self.target_manager.get_all_targets()
            if existing_targets:
                logger.warning(ansi.style(f"Database already contains {len(existing_targets)} targets:", fg=ansi.Fg.YELLOW))
                for target in existing_targets:
                    logger.info(f"  - {target['name']} ({target['target_id']})")
                
                overwrite = Input_Mgr.Instance().single_choice(
                    "How to handle existing targets?",
                    ["Skip existing (recommended)", "Overwrite existing", "Cancel import"]
                )
                
                if overwrite == "Cancel import":
                    logger.info("Import cancelled")
                    return
                
                force_overwrite = (overwrite == "Overwrite existing")
            else:
                force_overwrite = False
            
            # Import targets
            self.target_manager.parse_and_set_target_from_json(json_file, force_overwrite)
            logger.info(ansi.style(f"Import completed from {json_file}", fg=ansi.Fg.GREEN))
            
        except Exception as e:
            logger.error(ansi.style(f"Error importing targets: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Target Commands')
    def do_target_export(self, arg):
        'Export current database targets to JSON file'
        try:
            if not arg:
                json_file = Input_Mgr.Instance().string_input(
                    "Enter export file path (default: conf/target_export.json)"
                ) or "conf/target_export.json"
            else:
                json_file = arg.strip()
            
            # Export targets
            success = self.target_manager.export_targets_to_json(json_file, backup_original=True)
            
            if success:
                logger.info(ansi.style(f"Successfully exported targets to {json_file}", fg=ansi.Fg.GREEN))
            else:
                logger.error(ansi.style("Failed to export targets", fg=ansi.Fg.RED))
                
        except Exception as e:
            logger.error(ansi.style(f"Error exporting targets: {str(e)}", fg=ansi.Fg.RED))
