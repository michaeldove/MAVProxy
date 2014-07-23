#!/usr/bin/env python
'''Bonjour GCS discovery'''


import socket
import functools
import pybonjour
from pymavlink import mavutil
from MAVProxy.modules.lib import mp_module

class BonjourModule(mp_module.MPModule):
    """
    Discover Bonjour GCS services and auto connect.

    >>> class State:
    ...  select_extra = {}
    >>> mpstate = State()
    >>> module = BonjourModule(mpstate)
    Module discover loaded
    >>> mpstate.select_extra
    {3: (<function DNSServiceProcessResult ...>, <DNSServiceRef object ...>)}
    """

    REG_TYPE = '_gcs._udp.'
    BAUD = 115200

    def __init__(self, mpstate):
        super(BonjourModule, self).__init__(mpstate,
              "discover", "discover bonjour gcs services")
        self.connected_GCS = []
        self.discover_services()
        print("Module discover loaded")

    def discover_services(self):
        """Discover Bonjour services."""

        self.browse_sdRef = pybonjour.DNSServiceBrowse(
                                            regtype = self.REG_TYPE,
                                            callBack = self.browse_callback)
        self.register_service_descriptor(self.browse_sdRef,
                pybonjour.DNSServiceProcessResult)


    def should_connect_to_GCS(self, fullname, port):
        """ Determine if a connection to the GCS already exists."""
        return (fullname, port) not in self.connected_GCS

    def connect_to_GCS(self, fullname, ip_address, port):
        """Start output of MAVLink packets to GCS."""
        address = '%s:%s' % (ip_address, port)
        self.mpstate.mav_outputs.append(
                mavutil.mavlink_connection(address,
                                           baud=self.BAUD,
                                           input=False))
        self.register_connection_to_GCS(fullname, port)

    def register_connection_to_GCS(self, fullname, port):
        self.connected_GCS.append((fullname, port))

    def deregister_service_descriptor(self, serviceDescriptor):
        """Deregister a service descriptor from event polling."""
        del self.mpstate.select_extra[serviceDescriptor.fileno()]

    def register_service_descriptor(self, serviceDescriptor, handler):
        """Register a service descriptor for event polling."""
        self.mpstate.select_extra[serviceDescriptor.fileno()] = (
                handler, serviceDescriptor)

    def query_record_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, rrtype, rrclass, rdata, ttl, port, serviceName):
        """Callback when host has been resolved to an ip address."""

        if errorCode == pybonjour.kDNSServiceErr_NoError:
            ip_address = socket.inet_ntoa(rdata)

            self.deregister_service_descriptor(sdRef)

            if self.should_connect_to_GCS(fullname, port):
                self.connect_to_GCS(fullname, ip_address, port)

                print 'Connected to %s at %s:%d' % (
                        serviceName, ip_address, port)



    def resolve_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, hosttarget, port, txtRecord, serviceName):
        """Callback when service has been resolved to a host and port.""" 

        if errorCode == pybonjour.kDNSServiceErr_NoError:
            self.deregister_service_descriptor(sdRef)

            query_func = functools.partial(self.query_record_callback,
                                           port=port,
                                           serviceName=serviceName)
            query_sdRef = \
                pybonjour.DNSServiceQueryRecord(
                                        interfaceIndex = interfaceIndex,
                                        fullname = hosttarget,
                                        rrtype = pybonjour.kDNSServiceType_A,
                                        callBack = query_func,
                                        )

            self.register_service_descriptor(query_sdRef,
                    pybonjour.DNSServiceProcessResult)


    def browse_callback(self, sdRef, flags, interfaceIndex, errorCode,
            serviceName, regtype, replyDomain):
        """Callback when a service has been discovered."""

        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return

        if not (flags & pybonjour.kDNSServiceFlagsAdd):
            print 'Service removed'
            # TODO: Wireup service disconnection.
            return

        resolve_func = functools.partial(self.resolve_callback,
                                         serviceName=serviceName)
        resolve_sdRef = pybonjour.DNSServiceResolve(0,
                                                    interfaceIndex,
                                                    serviceName,
                                                    regtype,
                                                    replyDomain,
                                                    resolve_func)

        self.register_service_descriptor(resolve_sdRef,
                                       pybonjour.DNSServiceProcessResult)

    def mavlink_packet(self, m):
        '''handle an incoming mavlink packet'''
        pass



def init(mpstate):
    '''initialise module'''
    return BonjourModule(mpstate)

if __name__ == "__main__":
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS)
