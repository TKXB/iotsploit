#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from .base_commands import BaseCommands
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class TargetCommands(BaseCommands):
    """Target-related commands for the SAT Shell"""

    @cmd2.with_category('Target Commands')
    def do_list_targets(self, arg):
        'List all targets stored in the database'
        try:
            targets = self.target_manager.get_all_targets()
            
            if not targets:
                logger.info(ansi.style("No targets found in the database.", fg=ansi.Fg.YELLOW))
                return

            logger.info(ansi.style("Targets in the database:", fg=ansi.Fg.CYAN))
            for target in targets:
                logger.info(ansi.style(f"  - ID: {target['target_id']}", fg=ansi.Fg.GREEN))
                logger.info(f"    Name: {target['name']}")
                logger.info(f"    Type: {target['type']}")
                logger.info(f"    Status: {target['status']}")
                
                # All target types now have ip_address and location
                logger.info(f"    IP Address: {target.get('ip_address', 'N/A')}")
                logger.info(f"    Location: {target.get('location', 'N/A')}")
                
                logger.info(f"    Properties: {target['properties']}")
                logger.info("    ---")

        except Exception as e:
            logger.error(ansi.style(f"Error listing targets: {str(e)}", fg=ansi.Fg.RED))

    do_lst = do_list_targets

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
