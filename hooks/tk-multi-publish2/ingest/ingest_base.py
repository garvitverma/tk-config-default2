# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import pprint

import sgtk
from sgtk import TankError, TankMissingTemplateError, TankMissingTemplateKeysError


HookBaseClass = sgtk.get_hook_baseclass()


class IngestBasePlugin(HookBaseClass):
    """
    Base Ingest Plugin
    """

    def _create_vendor_task(self, item, step_entity):
        """
        Creates a Vendor Task for the Entity represented by the Context.

        :param item: Item to get the context from.
        :param step_entity: Step entity to create Task against.
        """

        # construct the data for the new Task entity
        data = {
            "step": step_entity,
            "project": item.context.project,
            "entity": item.context.entity if item.context.entity else item.context.project,
            "content": "Vendor",
            "sg_status_list": "na"
        }

        # create the task
        sg_result = self.sgtk.shotgun.create("Task", data)
        if not sg_result:
            self.logger.error("Failed to create new task - reason unknown!")
        else:
            self.logger.info("Created a Vendor Task.", extra={
                        "action_show_more_info": {
                            "label": "Show Task",
                            "tooltip": "Show the existing Task in Shotgun",
                            "text": "Task Entity: %s" % pprint.pformat(sg_result)
                        }
                    }
                )

    def _resolve_template_setting_value(self, setting, item):
        """Resolve the setting template value"""
        publisher = self.parent

        if not setting.value:
            return None

        # Start with the fields stored with the setting
        fields = {k: v.value for (k, v) in setting.extra["fields"].iteritems()}

        tmpl = publisher.get_template_by_name(setting.value)
        if not tmpl:
            # this template was not found in the template config!
            raise TankMissingTemplateError("The Template '%s' does not exist!" % setting.value)

        # First get the fields from the context
        try:
            context_fields = item.context.as_template_fields(tmpl)
            fields.update(context_fields)
            # update the properties context_fields
            item.properties.context_fields.update(context_fields)
        except TankError:
            self.logger.debug(
                "Unable to get context fields for publish_path_template.")

        missing_keys = tmpl.missing_keys(fields, True)
        # update the missing fields
        [item.properties.missing_fields.setdefault(key, None) for key in missing_keys]

        if missing_keys:
            raise TankMissingTemplateKeysError(
                "Cannot resolve Template (%s). Missing keys: %s" %
                (setting.value, pprint.pformat(missing_keys))
            )

        # Apply fields to template to get resolved value
        return tmpl.apply_fields(fields)

    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish.

        Returns a boolean to indicate validity.

        :param task_settings: Dictionary of settings
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

        # Run the context validations first.
        if not item.context.entity:
            self.logger.error("Ingestion at project level is not allowed! Please Contact TDs.")
            return False
        # context check needs to run before the other validations do.
        if not item.context.task:
            # Item doesn't contain a step entity! Intimate the user to create one, if they want to ingest.
            step_filters = list()
            step_filters.append(['short_name', 'is', "vendor"])

            # make sure we get the correct Step!
            # this should handle whether the Step is from Sequence/Shot/Asset
            step_filters.append(["entity_type", "is", item.context.entity["type"]])

            fields = ['entity_type', 'code', 'id']

            # add a vendor step to all ingested files
            step_entity = self.sgtk.shotgun.find_one(
                entity_type='Step',
                filters=step_filters,
                fields=fields
            )

            if not step_entity:
                self.logger.error("Step Entity doesn't exist. Please contact your TDs.",
                                  extra={
                                        "action_show_more_info": {
                                            "label": "Show Filters",
                                            "tooltip": "Show the filters used to query the Step.",
                                            "text": "SG Filters: %s\n"
                                                    "Fields: %s" % (pprint.pformat(step_filters),
                                                                    pprint.pformat(fields))
                                        }
                                    })

                return False

            task_filters = [
                ['step', 'is', step_entity],
                ['entity', 'is', item.context.entity],
                ['project', 'is', item.context.project],
                ['content', 'is', 'Vendor']
            ]

            task_fields = ['content', 'step', 'entity']

            task_entity = self.sgtk.shotgun.find_one(
                entity_type='Task',
                filters=task_filters,
                fields=task_fields
            )

            if task_entity:
                self.logger.warning(
                    "Vendor task already exists! Please select that task.",
                    extra={
                        "action_show_more_info": {
                            "label": "Show Task",
                            "tooltip": "Show the existing Task in Shotgun",
                            "text": "Task Entity: %s" % pprint.pformat(task_entity)
                        }
                    }
                )
            else:
                self.logger.error(
                    "Item doesn't have a valid Step.",
                    extra={
                        "action_button": {
                            "label": "Crt Vendor Task",
                            "tooltip": "Creates a Vendor Task on the Entity represented by the Context.",
                            "callback": lambda: self._create_vendor_task(item, step_entity)
                        }
                    }
                )

            return False

        try:
            # reset missing_fields and context_fields
            item.properties.missing_fields = dict()
            item.properties.context_fields = dict()
            # rest of the validations run after the context is verified.
            status = super(IngestBasePlugin, self).validate(task_settings, item)
        except TankMissingTemplateKeysError:
            # we want the user to fill these missing fields!
            self.logger.error(
                "Missing fields in the templates!",
                extra={
                    "action_show_more_info": {
                        "label": "Show Fields",
                        "tooltip": "Shows the missing fields across all templates.",
                        "text": "Missing Fields: %s\nContext Fields: %s" % (
                            pprint.pformat(item.properties.missing_fields),
                            pprint.pformat(item.properties.context_fields))
                    }
                }
            )
            status = False

        return status
