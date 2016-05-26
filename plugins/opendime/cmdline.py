#!/usr/bin/env python
#
# Opendime Plugin for...
# Electrum - lightweight Bitcoin client
# Copyright (C) 2016 Coinkite Inc.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from .shared import AttachedOpendime, has_libusb

from electrum.util import print_msg
from electrum.plugins import BasePlugin, hook

from electrum.commands import command

print "OD cmd imported"

@command('nw')          # needs: network, wallet
def od_capture():
    '''
        Move all funds from an unsealed Opendime into indicated wallet.
    '''
    print_msg('hello')
    pass

@command('n')           # needs: network
def od_info():
    '''
        Read balance and other details from an opendime
    '''
    print_msg('hello')
    pass

@command('')            # needs no wallet, nor network
def od_setup():
    '''
        Load a new Opendime with entropy so that it can pick it's private key.
    '''
    print_msg('hello')
    pass

class OpendimeCmdLineHandler:

    def stop(self):
        pass

    def show_message(self, msg):
        print_msg(msg)

    def prompt_auth(self, msg):
        import getpass
        print_msg(msg)
        response = getpass.getpass('')
        if len(response) == 0:
            return None
        return response

class Plugin(BasePlugin):
    handler = OpendimeCmdLineHandler()

    def is_enabled(self):
        return True
