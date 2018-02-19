# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import mimetypes
import os
import datetime
import glob
import pprint
import urllib
import sgtk
from sgtk import TankError

from dd.runtime import api
api.load("indiapipeline")

from indiapipeline.name_converter import NameConverter

HookBaseClass = sgtk.get_hook_baseclass()

print "HELLO CONFIG RUNNING!"

class IngestCollectorPlugin(HookBaseClass):
    """
    Collector that operates on the current set of ingestion files. Should
    inherit from the basic collector hook.
    """

    def _add_file_item(self, parent_item, path, is_sequence=False, seq_files=None):
        """
        Creates a file item
        """
        publisher = self.parent

        # get the file item from base class
        file_item = super(IngestCollectorPlugin, self)._add_file_item(parent_item, path, is_sequence, seq_files)

        converter = NameConverter()
        nc_template = converter.get_template_by_name("element_ingest_template")
        seq_path = publisher.util.get_path_for_frame(file_item.properties["path"], 1001)
        tokens = nc_template.get_tokens( os.path.split(seq_path)[1] )
        parent_item.properties["fields"] = tokens

        # resolve the {ENV} variable in work_path_template
        work_path_template = file_item.properties["work_path_template"]
        work_path_template = work_path_template.replace("{ENV}", self._resolve_env(file_item))

        # reassign the work_path_template property, after resolution of {ENV}
        if work_path_template:
            file_item.properties["work_path_template"] = work_path_template

        return file_item

    def on_context_changed(self, item):
        """
        Callback to update the item on context changes.

        :param item: The Item instance
        """
        # Set the item's fields property
        item.properties["fields"] = self._resolve_item_fields(item)

        self._build_new_context(item)

    def _build_new_context(self, item):
        """Updates the context of the item from the work_path_template, if needed.
        
        :param item: item from publisher.
        """
        publisher = self.parent
        if "fields" in item.properties:
            fields = item.properties["fields"]
            # we are using work_path_template in ingestion to spoof the path it's supposed to be published at
            # this path will then be used to resolve the new context.
            work_path_template = item.properties.get("work_path_template")
            if work_path_template:
                work_tmpl = publisher.get_template_by_name(work_path_template)
                if not work_tmpl:
                    # this template was not found in the template config!
                    raise TankError("The template '%s' does not exist!" % work_path_template)

            # once all the fields are set, construct a dummy work path
            # this path will help us re-construct the context!
            work_path = work_tmpl.apply_fields(fields)
            new_context = self.tank.context_from_path(work_path)

            from dd.runtime import api
            api.load("ipython")
            from IPython import embed
            embed()

            if item.context.entity:
                # if the previous context is not same as new context
                if not (item.context.entity["type"] == new_context.entity["type"] \
                    and item.context.entity["name"] == new_context.entity["name"]):
                        item.context = new_context
                        print "Old Context: ", item.context
                        print "Setting new Context: ", new_context
            # publisher launched from project context
            elif item.context.project:
                # if there is an entity in new_context, udpate it.
                # if there is still no entity, that means we are publishing it to project.
                if new_context.entity:
                    item.context = new_context
                    print "Old Context: ", item.context
                    print "Setting new Context: ", new_context


    def _resolve_env(self, item):
        """Returns the env name that's resolved for the given item.
        
        :param item: item from publisher.
        """

        parent_item = item.parent

        dd_fields = parent_item.properties["fields"]

        if "dd_shot" in dd_fields:
            if dd_fields["dd_shot"]:
                return 'shot'

        if "dd_sequence" in dd_fields:
            if dd_fields["dd_sequence"]:
                return 'sequence'

        if "dd_show" in dd_fields:
            if dd_fields["dd_show"]:
                return 'project'

    def _get_name_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        name_field = item.properties["fields"].get("dd_step")
        if name_field:
            return name_field

        elif item.parent:
            return self._get_workfile_name_field(item.parent)

        return None

    def _get_output_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        output_field = item.properties["fields"].get("dd_output")
        if output_field:
            return output_field

        return None

    def _get_sequence_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        sequence_field = item.properties["fields"].get("dd_sequence")
        if sequence_field:
            return sequence_field

        return None

    def _get_shot_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        shot_field = item.properties["fields"].get("dd_shot")
        if shot_field:
            return shot_field

        return None


    def _resolve_item_fields(self, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        publisher = self.parent

        fields = super(IngestCollectorPlugin, self)._resolve_item_fields(item)

        print "Fields from templ: ", fields

        # override name field, even if  it is defined
        # First attempt to get it from the parent item
        name_field = self._get_name_field_r(item.parent)
        if name_field:
            fields["name"] = name_field
            fields["Step"] = name_field

            # ---- Populate asset based keys in the item
            fields["sg_asset_type"] = name_field

        if "output" not in fields:
            # First attempt to get it from the parent item
            output_field = self._get_output_field_r(item.parent)
            if name_field:
                fields["output"] = output_field

                # ---- Populate asset based keys in the item
                fields["Asset"] = output_field
                
        if "Sequence" not in fields:
            # First attempt to get it from the parent item
            sequence_field = self._get_sequence_field_r(item.parent)
            if sequence_field:
                fields["Sequence"] = sequence_field

        if "Shot" not in fields:
            # First attempt to get it from the parent item
            shot_field = self._get_shot_field_r(item.parent)
            if shot_field:
                fields["Shot"] = shot_field

        print "FIELDS: ", fields        

        item.description = "Element ingest: {0} contains {1}".format(name_field, output_field)

        return fields
