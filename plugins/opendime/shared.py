from electrum.i18n import _


try:
    import usb.core

    has_libusb = True
except ImportError:
    has_libusb = False


class AttachedOpendime(object):

    pass
    
