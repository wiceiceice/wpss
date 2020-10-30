#!/usr/bin/python

"""
Communications Module
"""

import sys
import struct
import types

from errors import DecodingError, ConfigurationError
from debugging import ModuleLogger, DebugContents, bacpypes_debugging

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# prevent short/long struct overflow
_short_mask = 0xFFFFL
_long_mask = 0xFFFFFFFFL

# maps of named clients and servers
client_map = {}
server_map = {}

# maps of named SAPs and ASEs
service_map = {}
element_map = {}

#
#   String to Hex
#   Hex To String
#

def _str_to_hex(x, sep=''):
    return sep.join(["%02X" % (ord(c),) for c in x])

def _hex_to_str(x, sep=''):
    if sep:
        parts = x.split(sep)
    else:
        parts = [x[i:i+2] for i in range(0,len(x),2)]
    
    return ''.join(chr(int(part,16)) for part in parts)

#
#   PCI
#

@bacpypes_debugging
class PCI(DebugContents):

    _debug_contents = ('pduUserData+', 'pduSource', 'pduDestination')

    def __init__(self, *args, **kwargs):
        if _debug: PCI._debug("__init__ %r %r", args, kwargs)

        # split out the keyword arguments that belong to this class
        my_kwargs = {}
        other_kwargs = {}
        for element in ('user_data', 'source', 'destination'):
            if element in kwargs:
                my_kwargs[element] = kwargs[element]
        for kw in kwargs:
            if kw not in my_kwargs:
                other_kwargs[kw] = kwargs[kw]
        if _debug: PCI._debug("    - my_kwargs: %r", my_kwargs)
        if _debug: PCI._debug("    - other_kwargs: %r", other_kwargs)

        # call some superclass, if there is one
        super(PCI, self).__init__(*args, **other_kwargs)

        # pick up some optional kwargs
        self.pduUserData = my_kwargs.get('user_data', None)
        self.pduSource = my_kwargs.get('source', None)
        self.pduDestination = my_kwargs.get('destination', None)

    def update(self, pci):
        """Copy the PCI fields."""
        self.pduUserData = pci.pduUserData
        self.pduSource = pci.pduSource
        self.pduDestination = pci.pduDestination

    def pci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PCI._debug("pci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the values
        for k, v in (('user_data', self.pduUserData), ('source', self.pduSource), ('destination', self.pduDestination)):
            if _debug: PCI._debug("    - %r: %r", k, v)
            if v is None:
                continue

            if hasattr(v, 'dict_contents'):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__(k, v)

        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PCI._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        return self.pci_contents(use_dict=use_dict, as_class=as_class)

#
#   PDUData
#

@bacpypes_debugging
class PDUData(object):

    def __init__(self, data='', *args, **kwargs):
        if _debug: PDUData._debug("__init__ %r %r %r", data, args, kwargs)

        # this call will fail if there are args or kwargs, but not if there
        # is another class in the __mro__ of this thing being constructed
        super(PDUData, self).__init__(*args, **kwargs)

        # if this was passed a PDUData object, this
        # function acts like a copy constructor
        if isinstance(data, PDUData):
            self.pduData = data.pduData
        elif isinstance(data, str):
            self.pduData = data
        else:
            raise TypeError, "data must be PDUData or a string, was " + str(type(data))

    def get(self):
        if len(self.pduData) == 0:
            raise DecodingError, "no more packet data"

        ch = self.pduData[0]
        self.pduData = self.pduData[1:]
        return ord(ch)

    def get_data(self, dlen):
        if len(self.pduData) < dlen:
            raise DecodingError, "no more packet data"

        data = self.pduData[:dlen]
        self.pduData = self.pduData[dlen:]
        return data

    def get_short(self):
        return struct.unpack('>H',self.get_data(2))[0]

    def get_long(self):
        return struct.unpack('>L',self.get_data(4))[0]

    def put(self, ch):
        self.pduData += chr(ch)

    def put_data(self, data):
        self.pduData += data

    def put_short(self, n):
        self.pduData += struct.pack('>H',n & _short_mask)

    def put_long(self, n):
        self.pduData += struct.pack('>L',n & _long_mask)

    def debug_contents(self, indent=1, file=sys.stdout, _ids=None):
        if isinstance(self.pduData, types.StringType):
            if len(self.pduData) > 20:
                hexed = _str_to_hex(self.pduData[:20],'.') + "..."
            else:
                hexed = _str_to_hex(self.pduData,'.')
            file.write("%spduData = x'%s'\n" % ('    ' * indent, hexed))
        else:
            file.write("%spduData = %r\n" % ('    ' * indent, self.pduData))

    def pdudata_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PDUData._debug("pdudata_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # add the data if it is not None
        v = self.pduData
        if v is not None:
            if isinstance(v, types.StringType):
                v = _str_to_hex(v)
            elif hasattr(v, 'dict_contents'):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__('data', v)

        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: PDUData._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        return self.pdudata_contents(use_dict=use_dict, as_class=as_class)

#
#   PDU
#

@bacpypes_debugging
class PDU(PCI, PDUData):

    def __init__(self, data='', **kwargs):
        if _debug: PDU._debug("__init__ %r %r", data, kwargs)

        # pick up some optional kwargs
        user_data = kwargs.get('user_data', None)
        source = kwargs.get('source', None)
        destination = kwargs.get('destination', None)

        # carry source and destination from another PDU
        # so this can act like a copy constructor
        if isinstance(data, PDU):
            # allow parameters to override values
            user_data = user_data or data.pduUserData
            source = source or data.pduSource
            destination = destination or data.pduDestination

        # now continue on
        PCI.__init__(self, user_data=user_data, source=source, destination=destination)
        PDUData.__init__(self, data)

    def __str__(self):
        return '<%s %s -> %s : %s>' % (self.__class__.__name__,
            self.pduSource,
            self.pduDestination,
            _str_to_hex(self.pduData, '.')
            )

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

#
#   Client
#

@bacpypes_debugging
class Client:

    def __init__(self, cid=None):
        if _debug: Client._debug("__init__ cid=%r", cid)

        self.clientID = cid
        self.clientPeer = None
        if cid is not None:
            if client_map.has_key(cid):
                raise ConfigurationError, "already a client %r" % (cid,)
            client_map[cid] = self

            # automatically bind
            if server_map.has_key(cid):
                server = server_map[cid]
                if server.serverPeer:
                    raise ConfigurationError, "server %r already bound" % (cid,)
                    
                bind(self, server)
                
    def request(self, *args, **kwargs):
        if not self.clientPeer:
            raise ConfigurationError, "unbound client"
        self.clientPeer.indication(*args, **kwargs)

    def confirmation(self, *args, **kwargs):
        raise NotImplementedError, "confirmation must be overridden"

#
#   Server
#

@bacpypes_debugging
class Server:

    def __init__(self, sid=None):
        if _debug: Server._debug("__init__ sid=%r", sid)

        self.serverID = sid
        self.serverPeer = None
        if sid is not None:
            if server_map.has_key(sid):
                raise RuntimeError, "already a server %r" % (sid,)
            server_map[sid] = self

            # automatically bind
            if client_map.has_key(sid):
                client = client_map[sid]
                if client.clientPeer:
                    raise ConfigurationError, "client %r already bound" % (sid,)
                    
                bind(client, self)

    def indication(self, *args, **kwargs):
        raise NotImplementedError, "indication must be overridden"

    def response(self, *args, **kwargs):
        if not self.serverPeer:
            raise ConfigurationError, "unbound server"
        self.serverPeer.confirmation(*args, **kwargs)

#
#   Debug
#

@bacpypes_debugging
class Debug(Client, Server):

    def __init__(self, label=None, cid=None, sid=None):
        if _debug: Debug._debug("__init__ label=%r cid=%r sid=%r", label, cid, sid)

        Client.__init__(self, cid)
        Server.__init__(self, sid)

        # save the label
        self.label = label

    def confirmation(self, *args, **kwargs):
        print "Debug(%s).confirmation" % (self.label,)
        for i, arg in enumerate(args):
            print "    - args[%d]:" % (i,), arg
            if hasattr(arg, 'debug_contents'):
                arg.debug_contents(2)
        for key, value in kwargs.items():
            print "    - kwargs[%r]:" % (key,), value
            if hasattr(value, 'debug_contents'):
                value.debug_contents(2)

        if self.serverPeer:
            self.response(*args, **kwargs)
        
    def indication(self, *args, **kwargs):
        print "Debug(%s).indication" % (self.label,)
        for i, arg in enumerate(args):
            print "    - args[%d]:" % (i,), arg
            if hasattr(arg, 'debug_contents'):
                arg.debug_contents(2)
        for key, value in kwargs.items():
            print "    - kwargs[%r]:" % (key,), value
            if hasattr(value, 'debug_contents'):
                value.debug_contents(2)

        if self.clientPeer:
            self.request(*args, **kwargs)
        
#
#   Echo
#

@bacpypes_debugging
class Echo(Client, Server):

    def __init__(self, cid=None, sid=None):
        if _debug: Echo._debug("__init__ cid=%r sid=%r", cid, sid)

        Client.__init__(self, cid)
        Server.__init__(self, sid)
        
    def confirmation(self, *args, **kwargs):
        if _debug: Echo._debug("confirmation %r %r", args, kwargs)

        if self.serverPeer:
            self.request(*args, **kwargs)
        
    def indication(self, *args, **kwargs):
        if _debug: Echo._debug("indication %r %r", args, kwargs)

        if self.clientPeer:
            self.response(*args, **kwargs)

#
#   ServiceAccessPoint
#
#   Note that the SAP functions have been renamed so a derived class 
#   can inherit from both Client, Service, and ServiceAccessPoint 
#   at the same time.
#

@bacpypes_debugging
class ServiceAccessPoint:

    def __init__(self, sapID=None):
        if _debug: ServiceAccessPoint._debug("__init__(%s)", sapID)
            
        self.serviceID = sapID
        self.serviceElement = None
        
        if sapID is not None:
            if service_map.has_key(sapID):
                raise ConfigurationError, "already a service access point %r" % (sapID,)
            service_map[sapID] = self

            # automatically bind
            if element_map.has_key(sapID):
                element = element_map[sapID]
                if element.elementService:
                    raise ConfigurationError, "application service element %r already bound" % (sapID,)
                    
                bind(element, self)
                
    def sap_request(self, *args, **kwargs):
        if _debug: ServiceAccessPoint._debug("sap_request(%s) %r %r", self.serviceID, args, kwargs)
            
        if not self.serviceElement:
            raise ConfigurationError, "unbound service access point"
        self.serviceElement.indication(*args, **kwargs)

    def sap_indication(self, *args, **kwargs):
        raise NotImplementedError, "sap_indication must be overridden"

    def sap_response(self, *args, **kwargs):
        if _debug: ServiceAccessPoint._debug("sap_response(%s) %r %r", self.serviceID, args, kwargs)
            
        if not self.serviceElement:
            raise ConfigurationError, "unbound service access point"
        self.serviceElement.confirmation(*args,**kwargs)

    def sap_confirmation(self, *args, **kwargs):
        raise NotImplementedError, "sap_confirmation must be overridden"

#
#   ApplicationServiceElement
#

@bacpypes_debugging
class ApplicationServiceElement:

    def __init__(self, aseID=None):
        if _debug: ApplicationServiceElement._debug("__init__(%s)", aseID)
            
        self.elementID = aseID
        self.elementService = None
        
        if aseID is not None:
            if element_map.has_key(aseID):
                raise ConfigurationError, "already an application service element %r" % (aseID,)
            element_map[aseID] = self
        
            # automatically bind
            if service_map.has_key(aseID):
                service = service_map[aseID]
                if service.serviceElement:
                    raise ConfigurationError, "service access point %r already bound" % (aseID,)
                    
                bind(self, service)
                
    def request(self, *args, **kwargs):
        if _debug: ApplicationServiceElement._debug("request(%s)", self.elementID, args, kwargs)
            
        if not self.elementService:
            raise ConfigurationError, "unbound application service element"

        self.elementService.sap_indication(*args, **kwargs)

    def indication(self, *args, **kwargs):
        raise NotImplementedError, "indication must be overridden"

    def response(self, *args, **kwargs):
        if _debug: ApplicationServiceElement._debug("response(%s)", self.elementID, args, kwargs)
            
        if not self.elementService:
            raise ConfigurationError, "unbound application service element"

        self.elementService.sap_confirmation(*args,**kwargs)

    def confirmation(self, *args, **kwargs):
        raise NotImplementedError, "confirmation must be overridden"

#
#   NullServiceElement
#

class NullServiceElement:

    def indication(self, *args, **kwargs):
        pass

    def confirmation(self, *args, **kwargs):
        pass

#
#   DebugServiceElement
#

class DebugServiceElement:

    def indication(self, *args, **kwargs):
        print "DebugServiceElement(%s).indication" % (self.elementID,)
        print "    - args:", args
        print "    - kwargs:", kwargs

    def confirmation(self, *args, **kwargs):
        print "DebugServiceElement(%s).confirmation" % (self.elementID,)
        print "    - args:", args
        print "    - kwargs:", kwargs

#
#   bind
#

@bacpypes_debugging
def bind(*args):
    """bind a list of clients and servers together, top down."""
    if _debug: bind._debug("bind %r", args)

    # generic bind is pairs of names
    if not args:
        # find unbound clients and bind them
        for cid, client in client_map.items():
            # skip those that are already bound
            if client.clientPeer:
                continue
                
            if not cid in server_map:
                raise RuntimeError, "unmatched server %r" % (cid,)
            server = server_map[cid]
            
            if server.serverPeer:
                raise RuntimeError, "server already bound %r" % (cid,)
                
            bind(client, server)
            
        # see if there are any unbound servers
        for sid, server in server_map.items():
            if server.serverPeer:
                continue
                
            if not sid in client_map:
                raise RuntimeError, "unmatched client %r" % (sid,)
            else:
                raise RuntimeError, "mistery unbound server %r" % (sid,)
            
        # find unbound application service elements and bind them
        for eid, element in element_map.items():
            # skip those that are already bound
            if element.elementService:
                continue
                
            if not eid in service_map:
                raise RuntimeError, "unmatched element %r" % (cid,)
            service = service_map[eid]
            
            if server.serverPeer:
                raise RuntimeError, "service already bound %r" % (cid,)
                
            bind(element, service)
            
        # see if there are any unbound services
        for sid, service in service_map.items():
            if service.serviceElement:
                continue
                
            if not sid in element_map:
                raise RuntimeError, "unmatched service %r" % (sid,)
            else:
                raise RuntimeError, "mistery unbound service %r" % (sid,)
            
    # go through the argument pairs
    for i in xrange(len(args)-1):
        client = args[i]
        if _debug: bind._debug("    - client: %r", client)
        server = args[i+1]
        if _debug: bind._debug("    - server: %r", server)

        # make sure we're binding clients and servers
        if isinstance(client, Client) and isinstance(server, Server):
            client.clientPeer = server
            server.serverPeer = client

        # we could be binding application clients and servers
        elif isinstance(client, ApplicationServiceElement) and isinstance(server, ServiceAccessPoint):
            client.elementService = server
            server.serviceElement = client

        # error
        else:
            raise TypeError, "bind() requires a client and server"

        if _debug: bind._debug("    - bound")

