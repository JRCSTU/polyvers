#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Utils for building elaborate Commands/Sub-commands with traitlets Application.

## Examples:

To run a base command, use this code::

    cd = MainCmd.make_cmd(argv, **app_init_kwds)  ## `sys.argv` used if `argv` is `None`!
    cmd.start()

To run nested commands and print its output, use :func:`baseapp.chain_cmds()` like that::

    cmd = chain_cmds([MainCmd, Sub1Cmd, Sub2Cmd], argv)  ## `argv` without sub-cmds
    sys.exit(baseapp.pump_cmd(cmd.start()) and 0)

Of course you can mix'n match.

## Configuration and Initialization guidelines for *Spec* and *Cmd* classes

0. The configuration of :class:`HasTraits` instance gets stored in its ``config`` attribute.
1. A :class:`HasTraits` instance receives its configuration from 3 sources, in this order:

  a. code specifying class-attributes or running on constructors;
  b. configuration files (*json* or ``.py`` files);
  c. command-line arguments.

2. Constructors must allow for properties to be overwritten on construction; any class-defaults
   must function as defaults for any constructor ``**kwds``.

3. Some utility code depends on trait-defaults (i.e. construction of help-messages),
   so for certain properties (e.g. description), it is preferable to set them
   as traits-with-defaults on class-attributes.

4. Listen `Good Bait <https://www.youtube.com/watch?v=CE4bl5rk5OQ>`_ after 1:43.

.. [#] http://traitlets.readthedocs.io/
"""

from collections import OrderedDict
import contextlib
import io
import logging
import os
import re

from boltons.setutils import IndexedSet as iset

import os.path as osp

from . import fileutils as fu
from ._vendor import traitlets as trt
from ._vendor.traitlets import Bool, List, Unicode  # @UnresolvedImport
from ._vendor.traitlets import config as trc


def class2cmd_name(cls):
    name = cls.__name__
    if name.lower().endswith('cmd') and len(name) > 3:
        name = name[:-3]

    return (
        # Turns 'FOOBarCmd' --> 'FOO_Bar_Cmd'
        re.sub('(?<=[a-z0-9])([A-Z]+)', r'_\1', name).  # ('(?!^)([A-Z]+)')
        lower().
        # 'foo_bar_cmd' --> 'foo-bar-cmd'
        replace('_', '-'))


def first_line(doc):
    for l in doc.split('\n'):
        if l.strip():
            return l.strip()


def cmd_class_short_help(app_class):
    desc = app_class.description
    return first_line(isinstance(desc, str) and desc or app_class.__doc__)


def build_sub_cmds(*subapp_classes):
    """Builds an ordered-dictionary of ``cmd-name --> (cmd-class, help-msg)``. """
    return OrderedDict((class2cmd_name(sa), (sa, cmd_class_short_help(sa)))
                       for sa in subapp_classes)


def cmd_line_chain(cmd):
    """Utility returning the cmd-line(str) that launched a :class:`Cmd`."""
    return ' '.join(c.name for c in reversed(cmd.my_cmd_chain()))


def chain_cmds(app_classes, argv=None, **root_kwds):
    """
    Instantiate a list of ``[cmd, subcmd, ...]``, linking children to parents.

    :param app_classes:
        A list of cmd-classes: ``[root, sub1, sub2, app]``
        Note: you have to "know" the correct nesting-order of the commands ;-)
    :param argv:
        cmdline args passed to the root (1st) cmd only.
        Make sure they do not contain any sub-cmds.
        Like :meth:`initialize()`, if undefined, replaced with ``sys.argv[1:]``.
    :return:
        The root(1st) cmd to invoke :meth:`Aplication.start()`

    Apply the :func:`pump_cmd()` or `collect_cmd()` on the return instance.

    - Normally `argv` contain any sub-commands, and it is enough to invoke
      ``initialize(argv)`` on the root cmd.  This function shortcuts
      arg-parsing for subcmds with explict cmd-chaining in code.
    - This functions is the 1st half of :meth:`Cmd.launch_instance()`.
    """
    if not app_classes:
        raise ValueError("No cmds to chained passed in!")

    app_classes = list(app_classes)
    root = app = None
    for app_cl in app_classes:
        if not isinstance(app_cl, type(trc.Application)):
            raise ValueError("Expected an Application-class instance, got %r!" % app_cl)
        if not root:
            ## The 1st cmd is always orphan, and gets returned.
            root = app = app_cl(**root_kwds)
        else:
            app.subapp = app = app_cl(parent=app)
        app.initialize(argv)

    app_classes[0]._instance = app

    return root


class CfgFilesRegistry(contextlib.ContextDecorator):
    """
    Locate and account extensioned files (by default ``.json|.py``).

    - Collects a Locate and (``.json|.py``) files present in the `path_list`, or
    - Invoke this for every "manually" visited config-file, successful or not.
    - Files collected earlier should override next ones.
    """

    def __init__(self, supported_cfg_extensions='.json .py'.split()):
        """
        :param list supported_cfg_extensions:
            file extension (with dot) in the order to search.
        """
        self.supported_cfg_extensions = tuple(supported_cfg_extensions)
        self._visited_tuples = []

    #: A list of 2-tuples ``(folder, fname(s))`` with loaded config-files
    #: in ascending order (last overrides earlier).
    _visited_tuples = None

    @property
    def config_tuples(self):
        """
        The consolidated list of loaded 2-tuples ``(folder, fname(s))``.

        Sorted in descending order (1st overrides later).
        """
        return self._consolidate(self._visited_tuples)

    @staticmethod
    def _consolidate(visited_tuples):
        """
        Reverse and remove multiple, empty records.

        Example::

            >>> CfgFilesRegistry._consolidate([
            ... ('a/b/', None),
            ... ('a/b/', 'F1'),
            ... ('a/b/', 'F2'),
            ... ('a/b/', None),
            ... ('c/c/', None),
            ... ('c/c/', None),
            ... ('d/',   'F1'),
            ... ('d/',   None),
            ... ('c/c/', 'FF')])
            [('a/b/',   ['F1', 'F2']),
             ('c/c/',   []),
             ('d/',     ['F1']),
             ('c/c/',   ['FF'])]
        """
        consolidated = []
        prev = None
        for b, f in visited_tuples:
            if not prev:            # loop start
                prev = (b, [])
            elif prev[0] != b:      # new dir
                consolidated.append(prev)
                prev = (b, [])
            if f:
                prev[1].append(f)
        if prev:
            consolidated.append(prev)

        return consolidated

    def visit_file(self, fpath, loaded):
        """
        Invoke this in ascending order for every visited config-file.

        :param bool loaded:
            Loaded successful?
        """
        base, fname = osp.split(fpath)
        if loaded:
            self.collected_paths.add(fpath)
            pair = (base, fname)
        else:
            pair = (base, None)
        self._visited_tuples.append(pair)

    def collect_fpaths(self, path_list):
        """
        Collects all (``.json|.py``) files present in the `path_list`, (descending order).

        :param path_list:
            A list of paths (absolute, relative, dir or folders).
        :type path_list:
            List[Text]
        :return:
            fully-normalized paths, with ext
        """
        collected_paths = self.collected_paths = iset()
        cfg_exts = self.supported_cfg_extensions

        def try_file_extensions(basepath):
            loaded_any = False
            for ext in cfg_exts:
                f = fu.ensure_file_ext(basepath, ext)
                if f in collected_paths:
                    continue

                loaded = osp.isfile(f)
                self.visit_file(f, loaded=loaded)
                loaded_any |= loaded

            ## Load any files in `conf.d/`, alphabetically-sorted.
            #
            for ext in ('', ) + cfg_exts:
                if basepath.endswith(ext):
                    conf_d = fu.ensure_file_ext(basepath.rstrip(ext), '.d')
                    if os.path.isdir(conf_d):
                        for f in sorted(os.listdir(conf_d)):
                            loaded = f.endswith(cfg_exts)
                            self.visit_file(osp.join(conf_d, f),
                                            loaded=loaded)
                            loaded_any |= loaded

            return loaded_any

        def _derive_config_fpaths(path):  # -> List[Text]:
            """Return multiple *existent* fpaths for each config-file path (folder/file)."""

            p = fu.convpath(path)
            loaded_any = try_file_extensions(p)
            ## Do not strip ext if has matched WITH ext.
            if not loaded_any:
                try_file_extensions(osp.splitext(p)[0])

        for cf in path_list:
            _derive_config_fpaths(cf)

        return list(collected_paths)

    def head_folder(self):
        """The *last* existing visited folder (if any), even if not containing files."""
        for dirpath, _ in self.config_tuples:
            if osp.exists(dirpath):
                assert osp.isdir(dirpath), ("Expected to be a folder:", dirpath)
                return dirpath


class PathList(List):
    """Trait that splits unicode strings on `os.pathsep` to form a the list of paths."""
    def __init__(self, *args, **kwargs):
        return super().__init__(*args, trait=Unicode(), **kwargs)

    def validate(self, obj, value):
        """break all elements also into `os.pathsep` segments"""
        value = super().validate(obj, value)
        value = [cf2
                 for cf1 in value
                 for cf2 in cf1.split(os.pathsep)]
        return value

    def from_string(self, s):
        if s:
            s = s.split(osp.pathsep)
        return s


class CmdException(Exception):
    pass


class Spec(trc.Configurable):
    verbose = Bool(
        config=True,
        help="Set logging-level to DEBUG.")

    force = Bool(
        config=True,
        help="Force things to perform their duties without complaints.")

    dry_run = Bool(
        config=True,
        help="Do not write files - just pretend.")


class Cmd(trc.Application, Spec):
    "Common machinery for all (sub)commands."

    @classmethod
    def make_cmd(app, argv=None, **kwargs):
        """
        Instanciate, initialize and return application.

        :param argv:
            Like :meth:`initialize()`, if undefined, replaced with ``sys.argv[1:]``.

        - Tip: Apply :func:`pump_cmd()` on return values to process
          generators of :meth:`run()`.
        - This functions is the 1st half of :meth:`launch_instance()` which
          invokes and discards :meth:`start()` results.
        """
        ## Overriden just to return `start()`.
        cmd = app.instance(**kwargs)
        cmd.initialize(argv)

        return cmd

    def root_app(self):
        "Utility to travel up the cmd-chain."
        while self.parent:
            self = self.parent
        return self

    @trt.default('log')
    def _log_default(self):
        "Mimic log-hierarchies for Configurable; their loggers are not hierarchical. "
        cls = type(self)
        return logging.getLogger('%s.%s' % (cls.__module__, cls.__name__))

    @trt.default('name')
    def _name(self):
        """Without it, need to set `name` attr on every class."""
        name = class2cmd_name(type(self))
        return name

    @trt.default('description')
    def _desc(self):
        """Without it, need to set `description` attr on every class."""
        return type(self).__doc__

    ##########
    ## HELP ##
    ##########

    option_description = Unicode("""
        Options are convenience aliases to configurable class-params,
        as listed in the "Equivalent to" description-line of the aliases.
        To see all configurable class-params for some <cmd>, use::
            <cmd> --help-all
        or view help for specific parameter using::
            {appname} desc <class>.<param>
    """.strip())

    def _my_text_interpolations(self):
        return {'appname': '<set `appname` in `Cmd._my_text_interpolations()>',
                'cmd_chain': cmd_line_chain(self)}

    def emit_description(self):
        ## Overridden for interpolating app-name.
        txt = self.description or self.__doc__
        txt %= self._my_text_interpolations()
        for p in trc.wrap_paragraphs('%s: %s' % (cmd_line_chain(self), txt)):
            yield p
            yield ''

    def emit_options_help(self):
        """Yield the lines for the options part of the help."""
        if not self.flags and not self.aliases:
            return
        header = 'Options'
        yield header
        yield '=' * len(header)
        for p in trc.wrap_paragraphs(self.option_description % self._my_text_interpolations()):
            yield p
            yield ''

        for l in self.emit_flag_help():
            yield l
        for l in self.emit_alias_help():
            yield l
        yield ''

    def emit_examples(self):
        ## Overridden for interpolating app-name.
        if self.examples:
            txt = self.examples
            txt = txt.strip() % self._my_text_interpolations()
            yield "Examples"
            yield "--------"
            yield ''
            yield trc.indent(trc.dedent(txt))
            yield ''

    def emit_help_epilogue(self, classes=None):
        """Yield the very bottom lines of the help message.

        If classes=False (the default), print `--help-all` msg.
        """
        if not classes:
            interps = self._my_text_interpolations()
            yield trc.dedent("""
            --------
            - For available option, configuration-params & examples, use:
                  %(cmd_chain)s help (OR --help-all)
            - For help on specific classes/params, use:
                  %(appname)s config desc <class-or-param-1>...
            - To inspect configuration values:
                  %(appname)s config show <class-or-param-1>...
            """ % interps)

    ############
    ## CONFIG ##
    ############

    @trt.observe('parent')
    def _inherit_parent_cmd(self, change):
        if self.parent:
            parent = self.parent

            if parent.flags:
                if self.flags:
                    flags = dict(parent.flags)
                    flags.update(self.flags)
                else:
                    flags = parent.flags
                self.flags = flags

            if parent.aliases:
                if self.aliases:
                    aliases = dict(parent.aliases)
                    aliases.update(self.aliases)
                else:
                    aliases = parent.aliases
                self.aliases = aliases

    config_paths = PathList(
        help="""
        Absolute/relative folder/file path(s) to read "static" config-parameters from.

        - Sources for this parameter can either be CLI or ENV-VAR; since the loading
          of config-files depend on this parameter, file-configs are ignored.
        - Multiple values may be given and each one may be separated by '(sep)s'.
          Priority is descending, i.e. config-params from the 1st one overrides the rest.
        - For paths resolving to existing folders, the filenames `{basename}(.py|.json)`
          are appended and searched (in this order); otherwise, any file-extension
          is ignored, and the mentioned extensions are combined and searched.

        Tips:
          - Use `config infos` to view the actual paths/files loaded.
          - Use `config write` to produce a skeleton of the config-file.

        Examples:
          To read and apply in descending order: [~/my_conf, /tmp/conf.py, ~/.{appname}.json]
          you may issue:
              <cmd> --config-paths=~/my_conf(sep)s/tmp/conf.py  --Cmd.config_paths=~/.{appname}.jso
        """ % {'sep': osp.pathsep}
        ## TODO: Simplify path-loading when /ipython/traitlets#242 merged??
        #  NOTE: Patch default-value on `Cmd` so all subcmds load same configs.
    ).tag(config=True)

    _cfgfiles_registry = None

    @property
    def loaded_config_files(self):
        return self._cfgfiles_registry and self._cfgfiles_registry.config_tuples or []

    config_basename = Unicode(
        help=""""
        The config-file's basename (no path or extension) to search when not explicitly specified.

        By default, it's the root app's name, prefixed with a dot('.').
        """)

    @trt.default('config_basename')
    def _config_basename(self):
        return '.' + self.root_app().name

    def _collect_static_fpaths(self):
        """Return fully-normalized paths, with ext."""
        config_paths = self.config_paths
        self._cfgfiles_registry = CfgFilesRegistry()
        fpaths = self._cfgfiles_registry.collect_fpaths(config_paths)

        return fpaths

    def _read_config_from_json_or_py(self, cfpath):
        """
        :param str cfpath:
            The absolute config-file path with either ``.py`` or ``.json`` ext.
        """
        log = self.log
        loaders = {
            '.py': trc.PyFileConfigLoader,
            '.json': trc.JSONFileConfigLoader,
        }
        ext = osp.splitext(cfpath)[1]
        loader = loaders.get(str.lower(ext))
        assert loader, cfpath  # Must exist.

        config = None
        try:
            config = loader(cfpath, path=None, log=log).load_config()
        except trc.ConfigFileNotFound:
            ## Config-file deleted between collecting its name and reading it.
            pass
        except Exception as ex:
            if self.raise_config_file_errors:
                raise
            log.error("Failed loading config-file '%s' due to: %s",
                      cfpath, ex, exc_info=True)
        else:
            log.debug("Loaded config-file: %s", cfpath)

        return config

    def read_config_files(self):  # -> trc.Config
        """
        Load :attr:`config_paths` and maintain :attr:`config_registry`.

        :param config_paths:
            full normalized paths (descending order, 1st overrides the rest)
        :return:
            the static_config loaded

        - Configuration files are read and merged from ``.json`` and/or ``.py`` files
          in :attribute:`config_paths`.
        """
        ## Adapted from :meth:`load_config_file()` & :meth:`_load_config_files()`.
        config_paths = self._collect_static_fpaths()

        new_config = trc.Config()
        ## Registry to detect collisions.
        loaded = {}  # type: Dict[Text, Config]

        for cfpath in config_paths[::-1]:
            config = self._read_config_from_json_or_py(cfpath)
            if config:
                for filename, earlier_config in loaded.items():
                    collisions = earlier_config.collisions(config)
                    if collisions:
                        import json
                        self.log.warning(
                            "Collisions detected in %s and %s config files."
                            " %s has higher priority: %s",
                            filename, cfpath, cfpath,
                            json.dumps(collisions, indent=2)
                        )
                loaded[cfpath] = config

                new_config.merge(config)

        return new_config

    def write_default_config(self, config_file=None, force=False):
        if config_file:
            config_file = fu.convpath(config_file)
            if osp.isdir(config_file):
                config_file = osp.join(config_file, self.config_basename)
        elif self.config_paths:
            config_file = self.config_paths[0]
        else:
            raise AssertionError("No config-file given to write to!")

        config_file = fu.ensure_file_ext(config_file, '.py')

        is_overwrite = osp.isfile(config_file)
        if is_overwrite:
            if not force:
                raise CmdException("Config-file '%s' already exists!"
                                   "\n  Specify `--force` to overwrite." % config_file)
            else:
                import shutil
                from datetime import datetime

                now = datetime.now().strftime('%Y%m%d-%H%M%S%Z')
                backup_name = '%s-%s.py' % (osp.splitext(config_file)[0], now)
                shutil.move(config_file, backup_name)

                op_msg = ", old file renamed --> '%s'" % backup_name
        else:
            op_msg = ""

        self.log.info("Writting config-file '%s'%s...", config_file, op_msg)
        fu.ensure_dir_exists(os.path.dirname(config_file), 0o700)
        config_text = self.generate_config_file()
        with io.open(config_file, mode='wt') as fp:
            fp.write(config_text)

    all_app_configurables = List(
        help="""
        A sequence of all app configurables to feed into `config` sub-command.

        Defined either on :class:`Cmd` superclass or on *root-cmd*.
        """
    )

    #############
    ## STARTUP ##
    #############

    def my_cmd_chain(self):
        """Return the chain of cmd-classes starting from my self or subapp."""
        cmd_chain = []
        pcl = self.subapp if self.subapp else self
        while pcl:
            cmd_chain.append(pcl)
            pcl = pcl.parent

        return cmd_chain

    def _is_dispatching(self):
        """True if dispatching to another command."""
        return isinstance(self.subapp, trc.Application)  # subapp == trait | subcmd | None

    @trc.catch_config_error
    def initialize(self, argv=None):
        """
        Invoked after __init__() by `make_cmd()` to apply configs and build subapps.

        :param argv:
            If undefined, they are replaced with ``sys.argv[1:]``!

        It parses cl-args before file-configs, to detect sub-commands
        and update any :attr:`config_paths`, then it reads all file-configs, and
        then re-apply cmd-line configs as overrides (trick copied from `jupyter-core`).
        """
        self.parse_command_line(argv)
        if self._is_dispatching():
            ## Only the final child reads file-configs.
            #  Also avoid contaminations with user if generating-config.
            return

        static_config = self.read_config_files()
        static_config.merge(self.cli_config)

        self.update_config(static_config)

    def start(self):
        """Dispatches into sub-cmds (if any), and then delegates to :meth:`run().

        If overriden, better invoke :func:`super()`, but even better
        to override :meth:``run()`.
        """
        if self.subapp is None:
            res = self.run(*self.extra_args)

            return res

        return self.subapp.start()

    def run(self, *args):
        """Leaf sub-commands must inherit this instead of :meth:`start()` without invoking :func:`super()`.

        :param args:
            Invoked by :meth:`start()` with :attr:`extra_args`.

        By default, screams about using sub-cmds, or about doing nothing!
        """
        import ipython_genutils.text as tw

        assert self.subcommands, "Override run() method in cmd subclasses."

        if args:
            subcmd_msg = "unknown sub-command `%s`!" % args[0]
        else:
            subcmd_msg = "sub-command is missing!"
        subcmds = '\n'.join('  %10s: %s' % (k, desc) for k, (_, desc)
                            in self.subcommands.items())
        msg = tw.dedent(
            """
            %(cmd_chain)s: %(subcmd_msg)s

              Try one of:
            %(subcmds)s
            %(epilogue)s""") % {
                'subcmd_msg': subcmd_msg,
                'cmd_chain': cmd_line_chain(self),
                'subcmds': subcmds,
                'epilogue': '\n'.join(self.emit_help_epilogue()),
        }
        raise CmdException(msg)