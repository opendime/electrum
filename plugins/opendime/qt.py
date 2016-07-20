#!/usr/bin/env python
#
# Opendime Plugin for
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

import base64
import urllib
import sys
import requests

from PyQt4.QtGui import QApplication, QPushButton

from electrum.plugins import BasePlugin, hook
from electrum.i18n import _

from electrum_gui.qt.util import EnterButton, WindowModalDialog, Buttons
from electrum_gui.qt.util import OkButton, CloseButton
from PyQt4.Qt import QVBoxLayout, QHBoxLayout, QWidget
from PyQt4.Qt import QGridLayout, QPushButton, QCheckBox, QLabel
from functools import partial

from .shared import AttachedOpendime, has_libusb

BACKGROUND_TXT = _('''\
<h3>Opendime&trade; Helper Plugin</h3>
<p>
Makes setup, loading and spending from
Opendime disposable hardware bitcoins even easier.
</p><p>
Once this plugin is enabled:
</p>
<ul>
<li> If you connect a sealed Opendime, the balance will be shown
     and you can send funds to it directly.
<li> Funds from <b>unsealed</b> devices will be automatically sent to your wallet.
<li> Fresh devices will be setup with good quality entropy.
<li> Use the <b>Opendime</b> tab to do all this!
</ul>
<p>
Learn more about Opendime and get some for yourself
at <a href="https://opendime.com/electrum">Opendime.com</a>
</p>
<hr>
''')

class OpendimeTab(QWidget):
    def __init__(self, wallet, main_window):
        '''
            Each open wallet may have an Opendime tab.
        '''
        QWidget.__init__(self)

        # capture these
        self.wallet = wallet
        self.main_window = main_window

        # Make a new tab, and insert as second-last. Keeping 'console'
        # as last tab, since that's more important than us.
        tab_bar = main_window.tabs
        idx = tab_bar.count() - 1

        self.build_gui()

        tab_bar.insertTab(idx, self, _('Opendime') )

        #if self.wallet.is_watching_only():

    def build_gui(self):
        '''
            Build the GUi elements for the Opendime tab.
        '''

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(3, 1)

        label = QLabel(_('Opendime from/to'))
        grid.addWidget(label, 0, 0)

        vbox0 = QVBoxLayout()
        vbox0.addLayout(grid)

        hbox = QHBoxLayout()
        hbox.addLayout(vbox0)

        vbox = QVBoxLayout(self)
        vbox.addLayout(hbox)
        vbox.addStretch(1)
        ##vbox.addWidget(self.invoices_label)
        #vbox.addWidget(self.invoices_list)
        #vbox.setStretchFactor(self.invoices_list, 1000)

    def remove_gui(self):
        '''
            User has disabled the plugin, so remove the "Opendime" tab we added.
        '''
        tab_bar = self.main_window.tabs

        for idx in range(tab_bar.count()):
            if tab_bar.widget(idx) is not self:
                continue
            tab_bar.removeTab(idx)

class Plugin(BasePlugin):

    button_label = _("Send to Opendime")

    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.instances = set()

        # if we are enabled after the system has a wallet
        # open, then our "load_wallet" hook will not have
        # been called, and typically there is at least one
        # wallet already open. Find it, and add our tab.
        qa = QApplication.instance()
        if not qa:
            # During startup case (iff enabled during previous run)
            # we are called before Qt is started; which is fine. Don't
            # need to do anything, since load_wallet will happen
            pass
        else:
            # Look for open wallet windows. Ignore others.
            for win in qa.topLevelWidgets():
                wallet = getattr(win, 'wallet', None)
                if wallet:
                    self.load_wallet(wallet, win)

    @hook
    def load_wallet(self, wallet, main_window):
        '''
            After a new wallet is loaded, we are called here.

            Add an Opendime tab to the wallet window.
        '''

        instance = OpendimeTab(wallet, main_window)

        self.instances.add(instance)

    @hook
    def close_wallet(self, wallet):
        '''
            A wallet was closed, remove from our list of instances.
            Other cleanup will be based on Qt.
        '''
        delme = set()
        for t in self.instances:
            if t.wallet is wallet:
                delme.add(t)
        self.instances.difference_update(delme)

    def on_close(self):
        '''
            This plugin has been disabled. Remove the Opendime tab on all wallets.
        '''

        for t in self.instances:
            t.remove_gui()

        self.instances.clear()

    def requires_settings(self):
        '''
            Do we want a settings button (on plugins menu)? Yes.
        '''
        return True

    def settings_widget(self, window):
        '''
            Provide a widget to be shown inline on the plugin list/menu.
        '''
        return EnterButton(_('Settings'), partial(self.settings_dialog, window))

    def settings_dialog(self, window):
        '''
            Our settings dialog, which is mostly background info at this point.
        '''
        d = WindowModalDialog(window, _("Opendime Settings"))

        vbox = QVBoxLayout(d)
        blurb = QLabel(BACKGROUND_TXT)
        blurb.openExternalLinks = True
        vbox.addWidget(blurb)

        grid = QGridLayout()
        vbox.addLayout(grid)
        y = 0

        # MEH: not so interesting.
        if 0:
            # checkbox: always grab everything
            def on_change_grab(checked):
                self.config.set_key('od_grab', bool(checked))

            grab_checkbox = QCheckBox()
            grab_checkbox.setChecked(self.config.get("od_grab", False))
            grab_checkbox.stateChanged.connect(on_change_grab)

            grid.addWidget(QLabel(_('Always grab unsealed funds (no confirm)? ')), y, 0)
            grid.addWidget(grab_checkbox, y,1)
            y += 1

        # checkbox: do extra verification
        def on_change_verify(checked):
            self.config.set_key('od_verify', bool(checked))

        verify_checkbox = QCheckBox()
        verify_checkbox.setChecked(self.config.get("od_verify", False))
        verify_checkbox.stateChanged.connect(on_change_verify)

        grid.addWidget(QLabel(_(
            'Perform extra device authenticity checks (for the paranoid)? ')), y, 0)
        grid.addWidget(verify_checkbox, y,1)
        y += 1

        vbox.addStretch()
        vbox.addLayout(Buttons(CloseButton(d), OkButton(d)))

        return d.exec_()

