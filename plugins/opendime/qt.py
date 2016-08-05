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
import os
import requests
import sip

import webbrowser

from PyQt4.QtGui import QApplication, QPushButton

from electrum.plugins import BasePlugin, hook
from electrum.i18n import _

from electrum_gui.qt.util import EnterButton, WindowModalDialog, Buttons, MONOSPACE_FONT
from electrum_gui.qt.util import OkButton, CloseButton, MyTreeWidget, ThreadedButton
from electrum_gui.qt.qrcodewidget import QRCodeWidget
from PyQt4.Qt import QVBoxLayout, QHBoxLayout, QWidget, QPixmap, QTreeWidgetItem, QIcon
from PyQt4.Qt import QGridLayout, QPushButton, QCheckBox, QLabel, QMenu, QFont, QSize
from PyQt4.Qt import QDesktopServices, QUrl, QHeaderView, QFrame, QFontMetrics, QSpacerItem
from PyQt4.QtCore import pyqtSignal
from PyQt4.Qt import Qt
from functools import partial
from collections import OrderedDict

from .shared import AttachedOpendime, has_libusb
from . import  assets_rc

from electrum.util import block_explorer_URL

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


class OpendimeItem(QTreeWidgetItem):
    def __init__(self, unit):
        '''
            QTreeWidgetItem() for a single OD unit.
        '''
        self.unit = unit

        print "New OD: %r" % unit

        icon_name, status_text = self.display_status()

        addr = unit.address if not unit.is_new else '  -  '
        super(OpendimeItem, self).__init__([status_text, addr, '' if unit.is_new else '?'])

        self.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)

        # status column
        self.setIcon(0, QIcon(icon_name))

        # address column
        self.setFont(1, QFont(MONOSPACE_FONT))
        #self.setTextAlignment(1, Qt.AlignLeft)      # works, but there is a gap?

        # balance
        #self.setTextAlignment(2, Qt.AlignRight)      # balance

        # key value used for UID
        self.serial = unit.serial

    def display_status(self):
        '''
            Return an icon filename and a short string status for a unit.
        '''
        unit = self.unit

        if not unit.is_sealed:
            return ":icons/unlock.png", "Unsealed"

        if not unit.verify_level:
            return ":icons/expired.png", "INVALID"

        if unit.is_new:
            return ":icons/key.png", "Fresh"

        return ":icons/seal.png", "Ready"

class OpendimeDetailView:
    '''
        A GUI box that holds details about a single opendime unit
        and provides a few key common functions as buttons.
    '''
    def __init__(self, parent, main_window):

        self.main_window = main_window
        y = 0

        g2 = QGridLayout(parent)
        g2.setSpacing(4)
        g2.setColumnMinimumWidth(0, OpendimeTab.ADDR_TEXT_WIDTH * 1.2)

        self.qr = QRCodeWidget(fixedSize=180)
        g2.addWidget(self.qr, y, 0); y+=1

        self.address = QLabel()
        self.address.setFont(QFont(MONOSPACE_FONT))
        g2.addWidget(self.address, y, 0); y+=1

        self.status = QPushButton()
        self.status.setFlat(True)
        self.status.setAutoFillBackground(True)
        self.status.pressed.connect(self.on_status_click)
        g2.addWidget(self.status, y, 0); y+=1

        self.balance = QLabel("Balance Here")
        g2.addWidget(self.balance, y, 0); y+=1

        self.buttons = Buttons(QPushButton("Main"), QPushButton("Second"))
        #g2.addWidget(self.buttons, 3, 0)
        g2.addLayout(self.buttons, y, 0); y+=1

        self.blank()

    def show(self, item):
        '''
            Display the details about that item
        '''
        unit = item.unit
        self.current_item = item

        if unit.is_new:
            self.qr.hide()
            self.address.setText('-')
        else:
            self.address.setText(unit.address)
            self.qr.setData(unit.address)
            self.qr.show()

        icn, txt = item.display_status()
        self.status.setText(txt)
        self.status.setIcon(QIcon(icn))

        self.status.parent().show()

    def blank(self):
        '''
            Be emptiness.
        '''

        # best to just hide the whole frame.
        self.current_item = None
        self.status.parent().hide()

    def on_status_click(self):
        '''
            Show something for click on status
        '''
        unit = self.current_item.unit
        
        if unit.problem:
            msg = '- DO NOT USE -\n\n'
            msg += unit.problem + '\n\n'

            self.main_window.show_error(msg)
            return

        if unit.is_new:
            msg = 'Opendime is factory fresh and does not yet have a private key'
        elif unit.is_sealed:
            msg = 'Ready for use. Load funds and/or view balance.'
        elif not unit.is_sealed:
            msg = 'The seal has been broken. Sweep funds immediately from this Opendime.'
        else:
            msg = "I'm confused"

        self.main_window.show_message(msg)


class OpendimeTab(QWidget):

    # signals for slotting
    new_unit_sig = pyqtSignal(AttachedOpendime)
    scan_done_sig = pyqtSignal(list)

    # calculated a little later.
    ADDR_TEXT_WIDTH = None

    def __init__(self, wallet, main_window):
        '''
            Each open wallet may have an Opendime tab.
        '''
        QWidget.__init__(self)

        # P2PKH addresses will always be no wider than this size on screen.
        if not self.ADDR_TEXT_WIDTH:
            met = QFontMetrics(QFont(MONOSPACE_FONT))
            OpendimeTab.ADDR_TEXT_WIDTH = met.width("M") * 35

        # capture these
        self.wallet = wallet
        self.main_window = main_window

        # Make a new tab, and insert as second-last. Keeping 'console'
        # as last tab, since that's more important than us.
        tab_bar = main_window.tabs
        idx = tab_bar.count() - 1

        self.build_gui()

        tab_bar.insertTab(idx, self, _('Opendime') )

        # these will be OpendimeItem instances, in display order, key is serial number
        # table items (Qt widgets)
        self.attached = OrderedDict()

        #if self.wallet.is_watching_only():

        # connect slots
        self.new_unit_sig.connect(self.on_new_unit)
        self.scan_done_sig.connect(self.on_scan_done)

    def table_item_menu(self, position):
        item = self.table.itemAt(position)

        if not item:
            # item can be None if they click on a blank (unused) row.
            return

        menu = QMenu()

        # read what unit is associated w/ row
        unit = item.unit
        assert unit

        # reality check
        sn = unit.serial
        chk = self.attached[sn]
        assert chk == item

        if unit.problem:
            a = menu.addAction("- DO NOT USE -", lambda: None)
            a.setEnabled(False)
            a = menu.addAction(unit.problem, lambda: None)
            a.setEnabled(False)
            menu.addSeparator()

        if unit.is_new:
            menu.addAction(_("Pick key now (initialize)"), lambda: self.setup_unit(unit))

        else:
            addr = unit.address

            # adding a kinda header to menu
            a = menu.addAction(unit.address, lambda: None)
            a.setEnabled(False)
            menu.addSeparator()

            app = QApplication.instance()

            if not unit.is_sealed:
                menu.addAction(_("Import private key into Electrum"),
                                        lambda: self.import_value(unit))
                menu.addAction(_("Sweep funds (one time)"), lambda: self.sweep_value(unit))
                menu.addSeparator()
            else:
                menu.addAction(_("Pay to..."), lambda: self.main_window.pay_to_URI('bitcoin:'+addr))
                menu.addSeparator()

            # Maybe todo: could open as a new wallet; either watch-only or if unsealed,
            # as a full wallet, see Wallet.from_address() and Wallet.from_private_key()
            # Probably a bad idea and too obscure otherwise.

            menu.addAction(_("Copy to address clipboard"), 
                                lambda: app.clipboard().setText(unit.address))

            menu.addAction(_("Show as QR code"),
                lambda: self.main_window.show_qrcode(addr, 'Opendime', parent=self))
    

            # kinda words, but if they hit "next" goes to their wallet, etc.
            #menu.addAction(_("Request payment"), lambda: self.main_window.receive_at(addr))
            menu.addAction(_('History'), lambda: self.main_window.show_address(addr))

            url = block_explorer_URL(self.main_window.config, 'addr', addr)
            if url:
                menu.addAction(_("View on block explorer"), lambda: webbrowser.open(url))

        menu.addSeparator()
        menu.addAction(_("View Opendime page (local HTML)"), 
            lambda: webbrowser.open('file:'+os.path.join(unit.root_path, 'index.htm')))
        menu.addAction(_("Reveal Opendime files"), 
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(unit.root_path)))

        menu.exec_(self.table.viewport().mapToGlobal(position))


    def rescan_now(self):
        '''
            Slow task: look for units, update table and our state when found.
            Runs in a non-GUI thread.
        '''
        try:
            self.status_label.text = "Scanning now..."
            self.status_label.update()

            # search for any and all units presently connected.
            paths = AttachedOpendime.find()

            new = []
            found = []

            for pn in paths:
                unit = AttachedOpendime(pn)
                found.append(unit)
                if unit.serial not in self.attached:
                    new.append(unit)
                    unit.verify_wrapped()

                    self.new_unit_sig.emit(unit)

            msg = None
            if new:
                msg = "%d new units found" % len(new)
            elif not self.attached:
                msg = "No units found"
            else:
                msg = "No change: %d units" % len(self.attached)

            self.status_label.setText(msg)

            self.scan_done_sig.emit([u.serial for u in found])


        except Exception, e:
            print str(e)


    def build_gui(self):
        '''
            Build the GUI elements for the Opendime tab.
        '''

        grid = QGridLayout(self)
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(0)
        #grid.setColumnStretch(3, 1)

        prod = QLabel()
        prod.setPixmap(QPixmap(':od-plugin/prod-shot.png').scaledToWidth(300))
        grid.addWidget(prod, 0, 0)

        hp_link = QLabel('<center><a href="https://opendime.com/electrum">opendime.com</a>')
        hp_link.openExternalLinks = True
        grid.addWidget(hp_link, 1, 0)

        #logo = QLabel()
        #logo.setPixmap(QPixmap(':od-plugin/od-logo.png').scaledToWidth(100))
        #grid.addWidget(logo, 1, 0, 1, 1)

        frame = QFrame()
        frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.details = OpendimeDetailView(frame, self.main_window)

        grid.addItem(QSpacerItem(0, 0), 0, 3)
        grid.addWidget(frame, 0, 4, 2, 1)       # spans two rows

        #grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 10)
        grid.setColumnStretch(2, 10)

        # addItem(QLayoutItem *item, row, column, rowSpan=1, columnSpan = 1, alignment = 0)

        # second column: 2 rows: button + status
        self.rescan_button = ThreadedButton(_('Rescan Now'), self.rescan_now)
        #self.rescan_button.setIcon(QIcon(":od-plugin/od-logo.png"))
        grid.addWidget(self.rescan_button, 0, 1, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Startup...")
        grid.addWidget(self.status_label, 1, 1, alignment=Qt.AlignCenter)

        # Note: these column headers have already been translated elsewhere in project.
        self.table = MyTreeWidget(self, self.table_item_menu,
                            [ _('Status'), _('Address'), _('Balance')],
                            editable_columns=[])

        self.table.header().setResizeMode(QHeaderView.Stretch)

        grid.addItem(QSpacerItem(0, 20), 2, 0, 1, 4)

        grid.addWidget(self.table, 3, 0, 1, -1)

        # slots
        self.table.currentItemChanged.connect(self.on_item_select)

    def on_item_select(self, cur_item, old_item=None):
        '''
            Specifc opendime has been selected; display it's details.

            Can be None if item deleted or list now empty.
        '''
        print "Select: %r" % cur_item

        if cur_item:
            self.details.show(cur_item)
        else:
            self.details.blank()

    def on_new_unit(self, unit):
        '''
            New opendime found, and was added to Q.
        '''
        # add to gui and list
        item = OpendimeItem(unit)
        sn = unit.serial
        self.attached[sn] = item

        self.table.addChild(item)

    def on_scan_done(self, found_serials):
        '''
            Scan of drives is complete, and we found those serial number.
            Anything else in our list, is now disconnected.

            I was tempted to keep previously-attached units in the list,
            since for most operations we already know all we need to, but
            it's a privacy problem, and could lead to confusion. So our policy
            will be the Opendime has to be connected to interact with it.
            Add the address to your wallet (somehow?) if you want to watch it.
        '''
        missing = set(self.attached.keys()) - set(found_serials)

        # remove associated GUI objects
        for sn in missing:
            item = self.attached[sn]
            sip.delete(item)
            del self.attached[sn]

        # might need to select something new
        self.rethink_selection()

    def rethink_selection(self):
        '''
            Auto-select a unit when appropriate.
        '''
        sel = self.table.selectedItems()
        if sel:
            # something already selected
            return

        if not self.attached:
            # nothing to select
            return

        # always pick the bottom entry; it's the most recently connected
        item = self.attached[self.attached.keys()[-1]]
        item.setSelected(True)
        self.on_item_select(item)


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

