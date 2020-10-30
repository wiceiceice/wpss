#!/usr/bin/python

"""
PDU
"""

import re
import types
import socket
import struct

from errors import *

from debugging import ModuleLogger, bacpypes_debugging
from comm import PCI as _PCI, PDUData

# pack/unpack constants
_short_mask = 0xFFFFL
_long_mask = 0xFFFFFFFFL

# some debugging
_debug = 0
_log = ModuleLogger(globals())

def _str_to_hex(x, sep=''):
    return sep.join(["%02X" % (ord(c),) for c in x])

def _hex_to_str(x, sep=''):
    if sep:
        parts = x.split(sep)
    else:
        parts = [x[i:i+2] for i in range(0,len(x),2)]
    
    return ''.join([chr(int(part,16)) for part in parts])

#
#   Address
#

ip_address_mask_port_re = re.compile(r'^(?:(\d+):)?(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?(?::(\d+))?$')
ethernet_re = re.compile(r'^([0-9A-Fa-f][0-9A-Fa-f][:]){5}([0-9A-Fa-f][0-9A-Fa-f])$' )

class Address:
    nullAddr = 0
    localBroadcastAddr = 1
    localStationAddr = 2
    remoteBroadcastAddr = 3
    remoteStationAddr = 4
    globalBroadcastAddr = 5

    def __init__(self, *args):
        self.addrType = Address.nullAddr
        self.addrNet = None
        self.addrLen = 0
        self.addrAddr = ''

        if len(args) == 1:
            self.decode_address(args[0])
        elif len(args) == 2:
            self.decode_address(args[1])
            if self.addrType == Address.localStationAddr:
                self.addrType = Address.remoteStationAddr
                self.addrNet = args[0]
            elif self.addrType == Address.localBroadcastAddr:
                self.addrType = Address.remoteBroadcastAddr
                self.addrNet = args[0]
            else:
                raise ValueError, "unrecognized address ctor form"

    def decode_address(self, addr):
        """Initialize the address from a string.  Lots of different forms are supported."""
        # start out assuming this is a local station
        self.addrType = Address.localStationAddr
        self.addrNet = None

        if addr == "*":
            self.addrType = Address.localBroadcastAddr
            self.addrNet = None
            self.addrAddr = None
            self.addrLen = None

        elif addr == "*:*":
            self.addrType = Address.globalBroadcastAddr
            self.addrNet = None
            self.addrAddr = None
            self.addrLen = None

        elif isinstance(addr,types.IntType):
            if (addr < 0) or (addr >= 256):
                raise ValueError, "address out of range"
            self.addrAddr = chr(addr)
            self.addrLen = 1

        elif isinstance(addr,types.StringType):
            m = ip_address_mask_port_re.match(addr)
            if m:
                net, addr, mask, port = m.groups()
                if not mask: mask = '32'
                if not port: port = '47808'

                if net:
                    net = int(net)
                    if (net >= 65535):
                        raise ValueError, "network out of range"
                    self.addrType = Address.remoteStationAddr
                    self.addrNet = net

                self.addrPort = int(port)
                self.addrTuple = (addr,self.addrPort)

                addrstr = socket.inet_aton(addr)
                self.addrIP = struct.unpack('!L',addrstr)[0]
                self.addrMask = (-1L << (32 - int(mask))) & ((1 << 32) - 1)
                self.addrHost = (self.addrIP & ~self.addrMask)
                self.addrSubnet = (self.addrIP & self.addrMask)

                bcast = (self.addrSubnet | ~self.addrMask)
                self.addrBroadcastTuple = (socket.inet_ntoa(struct.pack('!L',bcast & _long_mask)),self.addrPort)

                self.addrAddr = addrstr + struct.pack('!H',self.addrPort & _short_mask)
                self.addrLen = 6

            elif ethernet_re.match(addr):
                self.addrAddr = _hex_to_str(addr, ':')
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^\d+$",addr):
                addr = int(addr)
                if (addr > 255):
                    raise ValueError, "address out of range"

                self.addrAddr = chr(addr)
                self.addrLen = 1

            elif re.match(r"^\d+:[*]$",addr):
                addr = int(addr[:-2])
                if (addr >= 65535):
                    raise ValueError, "network out of range"

                self.addrType = Address.remoteBroadcastAddr
                self.addrNet = addr
                self.addrAddr = None
                self.addrLen = None

            elif re.match(r"^\d+:\d+$",addr):
                net, addr = addr.split(':')
                net = int(net)
                addr = int(addr)
                if (net >= 65535):
                    raise ValueError, "network out of range"
                if (addr > 255):
                    raise ValueError, "address out of range"

                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = chr(addr)
                self.addrLen = 1

            elif re.match(r"^0x([0-9A-Fa-f][0-9A-Fa-f])+$",addr):
                self.addrAddr = _hex_to_str(addr[2:])
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^X'([0-9A-Fa-f][0-9A-Fa-f])+'$",addr):
                self.addrAddr = _hex_to_str(addr[2:-1])
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^\d+:0x([0-9A-Fa-f][0-9A-Fa-f])+$",addr):
                net, addr = addr.split(':')
                net = int(net)
                if (net >= 65535):
                    raise ValueError, "network out of range"

                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = _hex_to_str(addr[2:])
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^\d+:X'([0-9A-Fa-f][0-9A-Fa-f])+'$",addr):
                net, addr = addr.split(':')
                net = int(net)
                if (net >= 65535):
                    raise ValueError, "network out of range"

                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = _hex_to_str(addr[2:-1])
                self.addrLen = len(self.addrAddr)

            else:
                raise ValueError, "unrecognized format"

        elif isinstance(addr, types.TupleType):
            addr, port = addr
            self.addrPort = int(port)

            if isinstance(addr, types.StringType):
                if not addr:
                    # when ('', n) is passed it is the local host address, but that 
                    # could be more than one on a multihomed machine, the empty string 
                    # means "any".
                    addrstr = '\0\0\0\0'
                else:
                    addrstr = socket.inet_aton(addr)
                self.addrTuple = (addr, self.addrPort)
            elif isinstance(addr, types.LongType):
                addrstr = struct.pack('!L',addr & _long_mask)
                self.addrTuple = (socket.inet_ntoa(addrstr),self.addrPort)
            else:
                raise TypeError, "tuple must be (string, port) or (long, port)"

            self.addrIP = struct.unpack('!L',addrstr)[0]
            self.addrMask = -1L
            self.addrHost = None
            self.addrSubnet = None
            self.addrBroadcastTuple = self.addrTuple

            self.addrAddr = addrstr + struct.pack('!H',self.addrPort & _short_mask)
            self.addrLen = 6
        else:
            raise TypeError, "integer, string or tuple required"

    def __str__(self):
        if self.addrType == Address.nullAddr:
            return 'Null'
        elif self.addrType == Address.localBroadcastAddr:
            return '*'
        elif self.addrType == Address.localStationAddr:
            rslt = ''
            if self.addrLen == 1:
                rslt += str(ord(self.addrAddr[0]))
            else:
                port = ord(self.addrAddr[-2]) * 256 + ord(self.addrAddr[-1])
                if (len(self.addrAddr) == 6) and (port >= 47808) and (port <= 47823):
                    rslt += '.'.join(["%d" % ord(x) for x in self.addrAddr[0:4]])
                    if port != 47808:
                        rslt += ':' + str(port)
                else:
                    rslt += '0x' + _str_to_hex(self.addrAddr)
            return rslt
        elif self.addrType == Address.remoteBroadcastAddr:
            return '%d:*' % (self.addrNet,)
        elif self.addrType == Address.remoteStationAddr:
            rslt = '%d:' % (self.addrNet,)
            if self.addrLen == 1:
                rslt += str(ord(self.addrAddr[0]))
            else:
                port = ord(self.addrAddr[-2]) * 256 + ord(self.addrAddr[-1])
                if (len(self.addrAddr) == 6) and (port >= 47808) and (port <= 47823):
                    rslt += '.'.join(["%d" % ord(x) for x in self.addrAddr[0:4]])
                    if port != 47808:
                        rslt += ':' + str(port)
                else:
                    rslt += '0x' + _str_to_hex(self.addrAddr)
            return rslt
        elif self.addrType == Address.globalBroadcastAddr:
            return '*:*'
        else:
            raise TypeError, "unknown address type %d" % self.addrType

    def __repr__(self):
        return "<%s %s>" % (self.__class__.__name__, self.__str__())

    def __hash__(self):
        return hash( (self.addrType, self.addrNet, self.addrAddr) )

    def __eq__(self,arg):
        # try an coerce it into an address
        if not isinstance(arg, Address):
            arg = Address(arg)

        # all of the components must match
        return (self.addrType == arg.addrType) and (self.addrNet == arg.addrNet) and (self.addrAddr == arg.addrAddr)

    def __ne__(self,arg):
        return not self.__eq__(arg)

    def dict_contents(self, use_dict=None, as_class=None):
        """Return the contents of an object as a dict."""
        if _debug: _log.debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # exception to the rule of returning a dict
        return str(self)

#
#   pack_ip_addr, unpack_ip_addr
#

def pack_ip_addr((addr,port)):
    """Given an IP address tuple like ('1.2.3.4', 47808) return the six-octet string 
    useful for a BACnet address."""
    return socket.inet_aton(addr) + struct.pack('!H', port & _short_mask)

def unpack_ip_addr(addr):
    """Given a six-octet BACnet address, return an IP address tuple."""
    return (socket.inet_ntoa(addr[0:4]), struct.unpack('!H',addr[4:6])[0] )

#
#   LocalStation
#

class LocalStation(Address):

    def __init__(self, addr):
        self.addrType = Address.localStationAddr
        self.addrNet = None
        if isinstance(addr,types.IntType):
            if (addr < 0) or (addr >= 256):
                raise ValueError, "address out of range"
            self.addrAddr = chr(addr)
            self.addrLen = 1
        else:
            self.addrAddr = addr
            self.addrLen = len(addr)

#
#   RemoteStation
#

class RemoteStation(Address):

    def __init__(self, net, addr):
        if (net < 0) or (net >= 65535):
            raise ValueError, "network out of range"

        self.addrType = Address.remoteStationAddr
        self.addrNet = net
        if isinstance(addr,types.IntType):
            if (addr < 0) or (addr >= 256):
                raise ValueError, "address out of range"
            self.addrAddr = chr(addr)
            self.addrLen = 1
        else:
            self.addrAddr = addr
            self.addrLen = len(addr)

#
#   LocalBroadcast
#

class LocalBroadcast(Address):

    def __init__(self):
        self.addrType = Address.localBroadcastAddr
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None

#
#   RemoteBroadcast
#

class RemoteBroadcast(Address):

    def __init__(self,net):
        if (net < 0) or (net >= 65535):
            raise ValueError, "network out of range"

        self.addrType = Address.remoteBroadcastAddr
        self.addrNet = net
        self.addrAddr = None
        self.addrLen = None

#
#   GlobalBroadcast
#

class GlobalBroadcast(Address):

    def __init__(self):
        self.addrType = Address.globalBroadcastAddr
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None

#
#   PCI
#

@bacpypes_debugging
class PCI(_PCI):

    _debug_contents = ('pduExpectingReply', 'pduNetworkPriority')
    
    def __init__(self, *args, **kwargs):
        if _debug: PCI._debug("__init__ %r %r", args, kwargs)

        # split out the keyword arguments that belong to this class
        my_kwargs = {}
        other_kwargs = {}
        for element in ('expectingReply', 'networkPriority'):
            if element in kwargs:
                my_kwargs[element] = kwargs[element]
        for kw in kwargs:
            if kw not in my_kwargs:
                other_kwargs[kw] = kwargs[kw]
        if _debug: PCI._debug("    - my_kwargs: %r", my_kwargs)
        if _debug: PCI._debug("    - other_kwargs: %r", other_kwargs)

        # call some superclass, if there is one
        super(PCI, self).__init__(*args, **other_kwargs)

        # set the attribute/property values for the ones provided
        self.pduExpectingReply = my_kwargs.get('expectingReply', 0)     # see 6.2.2 (1 or 0)
        self.pduNetworkPriority = my_kwargs.get('networkPriority', 0)   # see 6.2.2 (0..3)

    def update(self, pci):
        """Copy the PCI fields."""
        _PCI.update(self, pci)
        
        # now do the BACnet PCI fields
        self.pduExpectingReply = pci.pduExpectingReply
        self.pduNetworkPriority = pci.pduNetworkPriority

    def pci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PCI._debug("pci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the parent class
        _PCI.pci_contents(self, use_dict=use_dict, as_class=as_class)

        # save the values
        use_dict.__setitem__('expectingReply', self.pduExpectingReply)
        use_dict.__setitem__('networkPriority', self.pduNetworkPriority)

        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PCI._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        return self.pci_contents(use_dict=use_dict, as_class=as_class)

#
#   PDU
#

@bacpypes_debugging
class PDU(PCI, PDUData):

    def __init__(self, *args, **kwargs):
        if _debug: PDU._debug("__init__ %r %r", args, kwargs)
        super(PDU, self).__init__(*args, **kwargs)

    def __str__(self):
        return '<%s %s -> %s : %s>' % (self.__class__.__name__, self.pduSource, self.pduDestination, _str_to_hex(self.pduData,'.'))

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PDUData._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call into the two base classes
        self.pci_contents(use_dict=use_dict, as_class=as_class)
        self.pdudata_contents(use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict

