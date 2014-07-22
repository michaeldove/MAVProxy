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
        self.connectedGCS = []
        self.discoverServices()
        print("Module discover loaded")

    def discoverServices(self):
        """Discover Bonjour services."""

        self.browse_sdRef = pybonjour.DNSServiceBrowse(
                                            regtype = self.REG_TYPE,
                                            callBack = self.browse_callback)
        self.registerServiceDescriptor(self.browse_sdRef,
                pybonjour.DNSServiceProcessResult)


    def mavlink_packet(self, m):
        '''handle an incoming mavlink packet'''
        pass

    def shouldConnectToGCS(self, fullname, port):
        """ Determine if a connection to the GCS already exists."""
        return (fullname, port) not in self.connectedGCS

    def connectToGCS(self, fullname, ip_address, port):
        """Start output of MAVLink packets to GCS."""
        address = '%s:%s' % (ip_address, port)
        self.mpstate.mav_outputs.append(
                mavutil.mavlink_connection(address,
                                           baud=self.baud,
                                           input=False))
        self.registerConnectionToGCS(fullname, port)

    def registerConnectionToGCS(self, fullname, port):
        self.connectedGCS.append((fullname, port))

    def deregisterServiceDescriptor(self, serviceDescriptor):
        """Deregister a service descriptor from event polling."""
        del self.mpstate.select_extra[serviceDescriptor.fileno()]

    def registerServiceDescriptor(self, serviceDescriptor, handler):
        """Register a service descriptor for event polling."""
        self.mpstate.select_extra[serviceDescriptor.fileno()] = (
                handler, serviceDescriptor)

    def query_record_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, rrtype, rrclass, rdata, ttl, port, serviceName):
        """Callback when host has been resolved to an ip address."""

        if errorCode == pybonjour.kDNSServiceErr_NoError:
            ip_address = socket.inet_ntoa(rdata)

            self.deregisterServiceDescriptor(sdRef)

            if self.shouldConnectToGCS(fullname, port):
                self.connectToGCS(fullname, ip_address, port)

                print 'Connected to %s at %s:%d' % (
                        serviceName, ip_address, port)



    def resolve_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, hosttarget, port, txtRecord, serviceName):
        """Callback when service has been resolved to a host and port.""" 

        if errorCode == pybonjour.kDNSServiceErr_NoError:
            self.deregisterServiceDescriptor(sdRef)

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

            self.registerServiceDescriptor(query_sdRef,
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

        self.registerServiceDescriptor(resolve_sdRef,
                                       pybonjour.DNSServiceProcessResult)

def init(mpstate):
    '''initialise module'''
    return BonjourModule(mpstate)

if __name__ == "__main__":
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS)
