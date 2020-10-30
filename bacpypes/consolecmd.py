#!/usr/bin/env python

"""
Console Command
"""

import sys
import types
import os
import gc
import readline
import signal
import cmd
import logging

from threading import Thread

from debugging import Logging, function_debugging, ModuleLogger
from consolelogging import ConsoleLogHandler

import core

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   console_interrupt
#

@function_debugging
def console_interrupt(*args):
    if _debug: console_interrupt._debug("console_interrupt %r", args)
    sys.stderr.write("Keyboard interrupt trapped - use EOF to end\n")

#
#   ConsoleCmd
#

class ConsoleCmd(cmd.Cmd, Thread, Logging):

    def __init__(self, prompt="> ", allow_exec=False, stdin=None, stdout=None):
        if _debug: ConsoleCmd._debug("__init__")
        cmd.Cmd.__init__(self, stdin=stdin, stdout=stdout)
        Thread.__init__(self, name="ConsoleCmd")

        # save the prompt and exec option
        self.prompt = prompt
        self.allow_exec = allow_exec

        # gc counters
        self.type2count = {}
        self.type2all = {}

        # logging handlers
        self.handlers = {}

        # execution space for the user
        self._locals  = {}
        self._globals = {}

        # set a INT signal handler, ^C will only get sent to the 
        # main thread and there's no way to break the readline
        # call initiated by this thread - sigh
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, console_interrupt)

        # start the thread
        self.start()

    def run(self):
        if _debug: ConsoleCmd._debug("run")

        # run the command loop
        self.cmdloop()
        if _debug: ConsoleCmd._debug("    - done cmdloop")

        # tell the main thread to stop, this thread will exit
        core.stop()

    def onecmd(self, cmdString):
        if _debug: ConsoleCmd._debug('onecmd %r', cmdString)

        # let the real command run, trapping errors
        try:
            rslt = cmd.Cmd.onecmd(self, cmdString)
        except Exception, e:
            ConsoleCmd._exception("exception: %r", e)

        # return what the command returned
        return rslt

    #-----

    def do_gc(self, args):
        """gc - print out garbage collection information"""

        # snapshot of counts
        type2count = {}
        type2all = {}
        for o in gc.get_objects():
            if type(o) == types.InstanceType:
                type2count[o.__class__] = type2count.get(o.__class__,0) + 1
                type2all[o.__class__] = type2all.get(o.__class__,0) + sys.getrefcount(o)

        # count the things that have changed
        ct = [ ( t.__module__
            , t.__name__
            , type2count[t]
            , type2count[t] - self.type2count.get(t,0)
            , type2all[t] - self.type2all.get(t,0)
            ) for t in type2count.iterkeys()
            ]

        # ready for the next time
        self.type2count = type2count
        self.type2all = type2all

        fmt = "%-30s %-30s %6s %6s %6s\n"
        self.stdout.write(fmt % ("Module", "Type", "Count", "dCount", "dRef"))

        # sorted by count
        ct.sort(lambda x, y: cmp(y[2], x[2]))
        for i in range(min(10,len(ct))):
            m, n, c, delta1, delta2 = ct[i]
            self.stdout.write(fmt % (m, n, c, delta1, delta2))
        self.stdout.write("\n")

        self.stdout.write(fmt % ("Module", "Type", "Count", "dCount", "dRef"))

        # sorted by module and class
        ct.sort()
        for m, n, c, delta1, delta2 in ct:
            if delta1 or delta2:
                self.stdout.write(fmt % (m, n, c, delta1, delta2))
        self.stdout.write("\n")

    def do_bugin(self, args):
        """bugin [ <logger> ]  - add a console logging handler to a logger"""
        args = args.split()
        if _debug: ConsoleCmd._debug("do_bugin %r", args)

        # get the logger name and logger
        if args:
            loggerName = args[0]
            if loggerName in logging.Logger.manager.loggerDict:
                logger = logging.getLogger(loggerName)
            else:
                logger = None
        else:
            loggerName = '__root__'
            logger = logging.getLogger()

        # add a logging handler
        if not logger:
            self.stdout.write("not a valid logger name\n")
        elif loggerName in self.handlers:
            self.stdout.write("%s already has a handler\n" % loggerName)
        else:
            handler = ConsoleLogHandler(logger)
            self.handlers[loggerName] = handler
            self.stdout.write("handler to %s added\n" % loggerName)
        self.stdout.write("\n")

    def do_bugout(self, args):
        """bugout [ <logger> ]  - remove a console logging handler from a logger"""
        args = args.split()
        if _debug: ConsoleCmd._debug("do_bugout %r", args)

        # get the logger name and logger
        if args:
            loggerName = args[0]
            if loggerName in logging.Logger.manager.loggerDict:
                logger = logging.getLogger(loggerName)
            else:
                logger = None
        else:
            loggerName = '__root__'
            logger = logging.getLogger()

        # remove the logging handler
        if not logger:
            self.stdout.write("not a valid logger name\n")
        elif not loggerName in self.handlers:
            self.stdout.write("no handler for %s\n" % loggerName)
        else:
            handler = self.handlers[loggerName]
            del self.handlers[loggerName]

            # see if this (or its parent) is a module level logger
            if hasattr(logger, 'globs'):
                logger.globs['_debug'] -= 1
            elif hasattr(logger.parent, 'globs'):
                logger.parent.globs['_debug'] -= 1

            # remove it from the logger
            logger.removeHandler(handler)
            self.stdout.write("handler to %s removed\n" % loggerName)
        self.stdout.write("\n")

    def do_buggers(self, args):
        """buggers  - list the console logging handlers"""
        args = args.split()
        if _debug: ConsoleCmd._debug("do_buggers %r", args)

        if not self.handlers:
            self.stdout.write("no handlers\n")
        else:
            self.stdout.write("handlers: ")
            self.stdout.write(', '.join(loggerName or '__root__' for loggerName in self.handlers))
            self.stdout.write("\n")

        loggers = logging.Logger.manager.loggerDict.keys()
        loggers.sort()
        for loggerName in loggers:
            if args and (not args[0] in loggerName):
                continue

            if loggerName in self.handlers:
                self.stdout.write("* %s\n" % loggerName)
            else:
                self.stdout.write("  %s\n" % loggerName)
        self.stdout.write("\n")

    #-----

    def do_exit(self, args):
        """Exits from the console."""
        if _debug: ConsoleCmd._debug("do_exit %r", args)
        return -1

    def do_EOF(self, args):
        """Exit on system end of file character"""
        if _debug: ConsoleCmd._debug("do_EOF %r", args)
        return self.do_exit(args)

    def do_shell(self, args):
        """Pass command to a system shell when line begins with '!'"""
        os.system(args)

    def do_help(self, args):
        """Get help on commands
        'help' or '?' with no arguments prints a list of commands for which help is available
        'help <command>' or '? <command>' gives help on <command>
        """
        ## The only reason to define this method is for the help text in the doc string
        cmd.Cmd.do_help(self, args)

    def preloop(self):
        """Initialization before prompting user for commands.
        Despite the claims in the Cmd documentaion, Cmd.preloop() is not a stub.
        """
        cmd.Cmd.preloop(self)   ## sets up command completion

        try:
            readline.read_history_file(sys.argv[0] + ".history")
        except Exception, e:
            if not isinstance(e, IOError):
                self.stdout.write("history error: %s\n" % e)

    def postloop(self):
        """Take care of any unfinished business.
        Despite the claims in the Cmd documentaion, Cmd.postloop() is not a stub.
        """
        try:
            readline.write_history_file(sys.argv[0]+".history")
        except Exception, e:
            self.stdout.write("history error: %s\n" % e)

        cmd.Cmd.postloop(self)   ## Clean up command completion

        self.stdout.write("Exiting...\n")
        core.stop()

    def precmd(self, line):
        """ This method is called after the line has been input but before
            it has been interpreted. If you want to modify the input line
            before execution (for example, variable substitution) do it here.
        """
        return line.strip()

    def postcmd(self, stop, line):
        """If you want to stop the console, return something that evaluates to true.
        If you want to do some post command processing, do it here.
        """
        return stop

    def emptyline(self):
        """Do nothing on empty input line"""
        pass

    def default(self, line):
        """Called on an input line when the command prefix is not recognized.
        If allow_exec is enabled, execute the line as Python code.
        """
        if not self.allow_exec:
            return cmd.Cmd.default(self, line)

        try:
            exec(line) in self._locals, self._globals
        except Exception, e:
            self.stdout.write("%s : %s\n" % (e.__class__, e))
