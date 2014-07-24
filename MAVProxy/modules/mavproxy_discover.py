#!/usr/bin/env python

# Bonjour GCS service discovery.
# Copyright 2014 Michael Dove
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


'''Bonjour GCS discovery'''


import socket
import functools
import pybonjour
from pymavlink import mavutil
from MAVProxy.modules.lib import mp_module

class BonjourModule(mp_module.MPModule):
    """
    Discover Bonjour GCS services and auto connect.

    >>> import mock
    >>> browse_patcher = mock.patch('pybonjour.DNSServiceBrowse')
    >>> resolve_patcher = mock.patch('pybonjour.DNSServiceResolve')
    >>> process_patcher = mock.patch('pybonjour.DNSServiceProcessResult')
    >>> mock_browse = browse_patcher.start()
    >>> mock_resolve = resolve_patcher.start()
    >>> mock_process = process_patcher.start()

    >>> def capture_browse_args(*args, **kwargs):
    ...  kwargs['callBack'](None, pybonjour.kDNSServiceFlagsAdd, 0, pybonjour.kDNSServiceErr_NoError, 'Mavlink', kwargs['regtype'], 'local')
    ...  return mock.DEFAULT


    def resolve_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, hosttarget, port, txtRecord, serviceName):

    >>> def capture_resolve_args(*args, **kwargs):
    ...  import pdb
    ...  pdb.set_trace()
    ...  func = args[5]
    ...  func(None, 0, 0, pybonjour.kDNSServiceErr_NoError, 'Mavlink', 'MAVLink.local', 1234, '')
    ...  return mock.DEFAULT

    >>> mock_browse.side_effect = capture_browse_args
    >>> browse_config = {'fileno': mock.Mock(return_value=1)}
    >>> mock_browse.return_value.configure_mock(**browse_config)

    >>> mock_resolve.side_effect = capture_resolve_args
    >>> resolve_config = {'fileno': mock.Mock(return_value=2)}
    >>> mock_resolve.return_value.configure_mock(**resolve_config)

    >>> mpstate = mock.MagicMock(select_extra={}, mav_outputs=[])
    >>> module = BonjourModule(mpstate)
    Module discover loaded
    >>> mpstate.select_extra
    {...: (<...>, <...>)}
    >>> first_key = mpstate.select_extra.keys()[0]
    >>> (func, sd) = mpstate.select_extra[first_key]
    >>> #func(sd)
    >>> mpstate.select_extra
    {...: (<...>, <...>), ...: (<...>, <...>)}
    >>> (func, sd) = list(set(mpstate.select_extra) - set((func, sd)))[0]
    >>> func(sd)
    >>> mpstate.select_extra
    {...: (<...>, <...>), ...: (<...>, <...>)}
    >>> (func, sd) = list(set(mpstate.select_extra) - set((func, sd)))[0]
    >>> func(sd)
    >>> mpstate.select_extra

    >>> browse_patcher.stop()
    >>> resolve_patcher.stop()
    >>> process_patcher.stop()
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

    def resolve_service(self, iface_idx, serv_name, reg_type, reply_domain):
        """Resolve discovered service."""

        resolve_func = functools.partial(self.resolve_callback,
                                         serviceName=serv_name)
        resolve_sdRef = pybonjour.DNSServiceResolve(0,
                                                    iface_idx,
                                                    serv_name,
                                                    reg_type,
                                                    reply_domain,
                                                    resolve_func)

        self.register_service_descriptor(resolve_sdRef,
                                       pybonjour.DNSServiceProcessResult)


    def query_host(self, iface_idx, serv_name, host, port):
        """Resolve host name to ip address."""
        query_func = functools.partial(self.query_record_callback,
                                       port=port,
                                       serviceName=serv_name)
        query_sdRef = \
            pybonjour.DNSServiceQueryRecord(
                                    interfaceIndex=iface_idx,
                                    fullname=host,
                                    rrtype=pybonjour.kDNSServiceType_A,
                                    callBack=query_func)
        self.register_service_descriptor(query_sdRef,
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


    def browse_callback(self, sdRef, flags, interfaceIndex, errorCode,
            serviceName, regtype, replyDomain):
        """Callback when a service has been discovered."""

        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return

        if not (flags & pybonjour.kDNSServiceFlagsAdd):
            print 'Service removed'
            # TODO: Wireup service disconnection.
            return

        self.resolve_service(interfaceIndex, serviceName, regtype, replyDomain)


    def resolve_callback(self, sdRef, flags, interfaceIndex, errorCode,
            fullname, hosttarget, port, txtRecord, serviceName):
        """Callback when service has been resolved to a host and port.""" 

        if errorCode == pybonjour.kDNSServiceErr_NoError:
            self.deregister_service_descriptor(sdRef)

            self.query_host(interfaceIndex, serviceName, hosttarget, port)


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




    def mavlink_packet(self, m):
        '''handle an incoming mavlink packet'''
        pass



def init(mpstate):
    '''initialise module'''
    return BonjourModule(mpstate)

if __name__ == "__main__":
    import doctest
    import mock
    doctest.testmod(optionflags=doctest.ELLIPSIS)
