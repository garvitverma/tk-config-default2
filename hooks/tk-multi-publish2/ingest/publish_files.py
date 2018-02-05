# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import copy
import glob
import pprint
import traceback

import sgtk
from sgtk import TankError

HookBaseClass = sgtk.get_hook_baseclass()

print "CONFIG! PUBLISH!"


DEFAULT_ITEM_TYPE_SETTINGS = {
    "file.alembic": {
        "publish_type": "Alembic Cache",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.3dsmax": {
        "publish_type": "3dsmax Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.nukestudio": {
        "publish_type": "NukeStudio Project",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.houdini": {
        "publish_type": "Houdini Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.maya": {
        "publish_type": "Maya Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.motionbuilder": {
        "publish_type": "Motion Builder FBX",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.nuke": {
        "publish_type": "Nuke Script",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.photoshop": {
        "publish_type": "Photoshop Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.render.sequence": {
        "publish_type": "Rendered Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.texture": {
        "publish_type": "Texture Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.image": {
        "publish_type": "Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.video": {
        "publish_type": "Movie",
        "publish_name_template": None,
        "publish_path_template": None
    },
}

class PublishFilesPlugin(HookBaseClass):
    """
    Plugin for creating generic publishes in Shotgun.

    This plugin is typically configured to act upon files that are dragged and
    dropped into the publisher UI. It can also be used as a base class for
    other file-based publish plugins as it contains standard operations for
    validating and registering publishes with Shotgun.

    Once attached to a publish item, the plugin will key off of properties that
    are set on the item. These properties can be set via the collector or
    by subclasses prior to calling methods on this class.

    The only property that is required for the plugin to operate is the ``path``
    property. All of the properties and settings understood by the plugin are
    documented below:

        Item properties
        -------------

        path - The path to the file to be published.

        sequence_paths - If set, implies the "path" property represents a
            sequence of files (typically using a frame identifier such as %04d).
            This property should be a list of files on disk matching the "path".

        is_sequence - A boolean defining whether or not this item is a sequence of files.

        publish_dependencies - A list of files to include as dependencies when
            registering the publish. If the item's parent has been published,
            it's path will be appended to this list.

        Task settings
        -------------------

        publish_type - If set in the plugin settings dictionary, will be
            supplied to SG as the publish type when registering "path" as a new
            publish. This is required.

        publish_name_template - If set in the plugin settings dictionary, will be
            supplied to SG as the publish name when registering the new publish.
            If not available, will fall back to the ``path_info`` hook logic.

        publish_path_template - If set in the plugin settings dictionary, used to
            determine where "path" should be copied prior to publishing. If
            not specified, "path" will be published in place.

    This plugin will also set the following properties on the item which may be 
    useful for child items.

        publish_type - Shotgun PublishedFile instance type.

        publish_name - Shotgun PublishedFile instance name.

        publish_version - Shotgun PublishedFile instance version.

        publish_path - The location on disk the publish is copied to.

        sg_publish_data - The dictionary of publish information returned from
            the tk-core register_publish method.

    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """
        # look for icon one level up from this hook's folder in "icons" folder
        return self.parent.expand_path("{self}/hooks/icons/publish.png")

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish File(s)"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        Publishes the file to the specified <b>Publish Path</b> location and
        creates a <b>PublishedFile</b> entity in Shotgun, which will include a
        reference to the file's published path on disk. Other users will be able
        to access the published file via the <b><a href='%s'>Loader</a></b> so
        long as they have access to the file's location on disk.

        <h3>Overwriting an existing publish</h3>
        Since all publishes are made immediately available to all consumers, a
        publish <b>cannot</b> be overwritten once it has been created. This is
        to ensure consistency and reproducibility for any consumers of the
        publish, such as downstream users or processes.
        """ % (loader_url,)

    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default_value": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts
        as part of its environment configuration.
        """
        schema = super(PublishFilesPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["file.*"]
        schema["Item Type Settings"]["default_value"] = DEFAULT_ITEM_TYPE_SETTINGS
        schema["Item Type Settings"]["values"]["items"] = {
            "publish_type": {
                "type": "shotgun_publish_type",
                "description": "",
            },
            "publish_name_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "version", "[output]", "[name]", "*"],
                "allows_empty": True,
            },
            "publish_path_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "*"],
                "allows_empty": True,
            },
        }
        return schema


    def accept(self, task_settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # Run the parent acceptance method
        accept_data = super(PublishFilesPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        path = item.properties.get("path")
        if not path:
            msg = "'path' property is not set for item: %s" % item.name
            accept_data["extra_info"] = {
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": msg
                }
            }
            accept_data["accepted"] = False
            return accept_data

        # return the accepted data
        return accept_data


    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish.

        Returns a boolean to indicate validity.

        :param task_settings: Dictionary of settings
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

         # {'fields': {'DD': 25,
         #  'MM': 1,
         #  'SEQ': 'FORMAT: %d',
         #  'Sequence': 'GDR',
         #  'Shot': '050020',
         #  'Step': 'light',
         #  'YYYY': 2018,
         #  'extension': 'exr',
         #  'eye': '%V',
         #  'height': 2376,
         #  'name': 'light',
         #  'output': 'beamsBty',
         #  'version': 2,
         #  'width': 4506},
         # 'is_sequence': True,
         # 'path': '/dd/shows/LEMONY/REF/CLIENT_VAULT/incoming/20180112/GDR_with_Enviro_CG_Rendered_Pt2/GDR_with_Enviro_CG_Rendered_Pt2/gdr050020_light_beams_bty_v02.fh10/gdr050020_light_beams_bty_v02.%04d.exr',
         # 'publish_name': 'gdr050020_light_beams_bty.####.exr',
         # 'publish_path': '/dd/shows/LEMONY/GDR/050020/SHARED/IMG/light/light/v002/4506x2376/GDR_050020_light_light-beamsBty.v002.%04d.exr',
         # 'publish_type': 'Rendered Image',
         # 'publish_version': 2,
         # 'sequence_paths': ['/dd/shows/LEMONY/REF/CLIENT_VAULT/incoming/20180112/GDR_with_Enviro_CG_Rendered_Pt2/GDR_with_Enviro_CG_Rendered_Pt2/gdr050020_light_beams_bty_v02.fh10/gdr050020_light_beams_bty_v02.1017.exr'],
         # 'work_path_template': 'shot_publish_render'}


        publisher = self.parent

        # ---- ensure that work file(s) exist on disk to be published

        if item.properties["is_sequence"]:
            if not item.properties["sequence_paths"]:
                self.logger.warning("File sequence does not exist: %s" % item.properties["path"])
                return False
        else:
            if not os.path.exists(item.properties["path"]):
                self.logger.warning("File does not exist: %s" % item.properties["path"])
                return False

        # ---- validate the settings required to publish

        attr_list = ("publish_type", "publish_path", "publish_name", "publish_version")
        for attr in attr_list:
            try:
                method = getattr(self, "_get_%s" % attr)
                item.properties[attr] = method(item, task_settings)
            except Exception:
                self.logger.error(
                    "Unable to determine '%s' for item: %s" % (attr, item.name),
                    extra={
                        "action_show_more_info": {
                            "label": "Show Error Log",
                            "tooltip": "Show the error log",
                            "text": traceback.format_exc()
                        }
                    }
                )
                return False

        # ---- check for conflicting publishes of this path with a status

        # Note the name, context, and path *must* match the values supplied to
        # register_publish in the publish phase in order for this to return an
        # accurate list of previous publishes of this file.
        publishes = publisher.util.get_conflicting_publishes(
            item.context,
            item.properties["publish_path"],
            item.properties["publish_name"],
            filters=["sg_status_list", "is_not", None]
        )

        if publishes:
            conflict_info = (
                "If you continue, these conflicting publishes will no longer "
                "be available to other users via the loader:<br>"
                "<pre>%s</pre>" % (pprint.pformat(publishes),)
            )
            self.logger.warning(
                "Found %s conflicting publishes in Shotgun" %
                    (len(publishes),),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting publishes in Shotgun",
                        "text": conflict_info
                    }
                }
            )

        # ---- ensure the published file(s) don't already exist on disk

        conflict_info = None
        if item.properties["is_sequence"]:
            seq_pattern = publisher.util.get_path_for_frame(item.properties["publish_path"], "*")
            seq_files = [f for f in glob.iglob(seq_pattern) if os.path.isfile(f)]

            if seq_files:
                conflict_info = (
                    "The following files already exist!<br>"
                    "<pre>%s</pre>" % (pprint.pformat(seq_files),)
                )
        else:
            if os.path.exists(item.properties["publish_path"]):
                conflict_info = (
                    "The following file already exists!<br>"
                    "<pre>%s</pre>" % (item.properties["publish_path"],)
                )

        if conflict_info:
            self.logger.error(
                "Version '%s' of this file already exists on disk." %
                    (item.properties["publish_version"],),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting published files",
                        "text": conflict_info
                    }
                }
            )
            return False

        self.logger.info(
            "A Publish will be created for item '%s'." %
                (item.name,),
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "Publish Path: %s" % (item.properties["publish_path"],)
                }
            }
        )

        # from dd.runtime import api
        # api.load("ipython")
        # from IPython import embed
        # embed()

        return True


    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and task_settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent

        # Get item properties populated by validate method
        publish_name     = item.properties["publish_name"]
        publish_path     = item.properties["publish_path"]
        publish_type     = item.properties["publish_type"]
        publish_version  = item.properties["publish_version"]

        # handle copying of work to publish
        self._copy_files(publish_path, item)

        # if the parent item has a publish path, include it in the list of
        # dependencies
        dependency_paths = item.properties.get("publish_dependencies", [])
        if "sg_publish_path" in item.parent.properties:
            dependency_paths.append(item.parent.properties["sg_publish_path"])

        # arguments for publish registration
        self.logger.info("Registering publish...")
        publish_data= {
            "tk": publisher.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": publish_name,
            "version_number": publish_version,
            "thumbnail_path": item.get_thumbnail_as_path() or "",
            "published_file_type": publish_type,
            "dependency_paths": dependency_paths
        }

        # log the publish data for debugging
        self.logger.debug(
            "Populated Publish data...",
            extra={
                "action_show_more_info": {
                    "label": "Publish Data",
                    "tooltip": "Show the complete Publish data dictionary",
                    "text": "<pre>%s</pre>" % (pprint.pformat(publish_data),)
                }
            }
        )

        # create the publish and stash it in the item properties for other
        # plugins to use.
        item.properties["sg_publish_data"] = sgtk.util.register_publish(
            **publish_data)
        self.logger.info("Publish registered!")


    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once
        all the publish tasks have completed, and can for example
        be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent

        # get the data for the publish that was just created in SG
        publish_data = item.properties["sg_publish_data"]

        # ensure conflicting publishes have their status cleared
        publisher.util.clear_status_for_conflicting_publishes(
            item.context, publish_data)

        self.logger.info(
            "Cleared the status of all previous, conflicting publishes")

        path = item.properties["path"]
        self.logger.info(
            "Publish created for file: %s" % (path,),
            extra={
                "action_show_in_shotgun": {
                    "label": "Show Publish",
                    "tooltip": "Open the Publish in Shotgun.",
                    "entity": publish_data
                }
            }
        )


    ############################################################################
    # protected methods

    def _get_publish_type(self, item, task_settings):
        """
        Get a publish type for the supplied item.

        :param item: The item to determine the publish type for

        :return: A publish type or None if one could not be found.
        """
        publish_type = task_settings.get("publish_type")
        if not publish_type:
            raise TankError("publish_type not set for item: %s" % item.name)

        return publish_type

    def _resolve_env(self, item):
        """Returns the env name that's resolved for the given item.
        
        :param item: item from publisher.
        """

        dd_fields = item.properties["fields"]

        if "Shot" in dd_fields:
            if dd_fields["Shot"]:
                return 'shot'

        if "Sequence" in dd_fields:
            if dd_fields["Sequence"]:
                return 'sequence'

        return 'project'

    def _get_publish_path(self, item, task_settings):
        """
        Get a publish path for the supplied item.

        :param item: The item to determine the publish type for

        :return: A string representing the output path to supply when
            registering a publish for the supplied item

        Extracts the publish path via the configured publish templates
        if possible.
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_path_template = task_settings.get("publish_path_template")
        publish_path_template = publish_path_template.replace("{ENV}", self._resolve_env(item))
        publish_path = None

        # If a template is defined, get the publish path from it
        if publish_path_template:

            pub_tmpl = publisher.get_template_by_name(publish_path_template)
            if not pub_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_path_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_path_template.")

            missing_keys = pub_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_path_template (%s). Missing keys: %s" %
                            (publish_path_template, pprint.pformat(missing_keys))
                )

            # Apply fields to publish_path_template to get publish path
            publish_path = pub_tmpl.apply_fields(fields)
            self.logger.debug(
                "Used publish_path_template to determine the publish path: %s" %
                (publish_path,)
            )

        # Otherwise fallback to publishing in place
        else:
            publish_path = item.properties["path"]
            self.logger.debug(
                "No publish_path_template defined. Publishing in place.")

        return publish_path


    def _get_publish_version(self, item, task_settings):
        """
        Get the publish version for the supplied item.

        :param item: The item to determine the publish version for

        Extracts the publish version from the item's "version" field
        """

        # Get the publish version from the item's fields
        return item.properties["fields"].get("version", 1)


    def _get_publish_name(self, item, task_settings):
        """
        Get the publish name for the supplied item.

        :param item: The item to determine the publish version for

        Uses the path info hook to retrieve the publish name.
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_name_template = task_settings.get("publish_name_template")
        publish_name = None

        # First check if we have a publish_name_template defined and attempt to
        # get the publish name from that
        if publish_name_template:

            pub_tmpl = publisher.get_template_by_name(publish_name_template)
            if not pub_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_name_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_name_template.")

            missing_keys = pub_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_name_template (%s). Missing keys: %s" %
                            (publish_name_template, pprint.pformat(missing_keys))
                )

            publish_name = pub_tmpl.apply_fields(fields)
            self.logger.debug(
                "Retrieved publish_name via publish_name_template.")

        # Otherwise fallback on file path parsing
        else:
            # Use built-in method for determining publish_name
            publish_name = publisher.util.get_publish_name(item.properties["path"])
            self.logger.debug(
                "Retrieved publish_name via source file path.")

        return publish_name
