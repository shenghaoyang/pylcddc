"""
exceptions.py

Module containing the exceptions used by the pylcddc package

Contains the following exceptions:
    - ``PylcddcError``: base class for all exceptions related to pylcddc
    - ``ProtocolVersionError``: used on protocol version
                                mismatch between client and server
    - ``RequestError``: used for non-fatal request error returned by
                        LCDd in response to a pylcddc request
    - ``FatalError``: used to indicate to applications that a fatal library
                      error has occured.

Copyright Shenghao Yang, 2018

See LICENSE.txt.txt for more details.
"""

from typing import Sequence


class PylcddcError(Exception):
    """
    Base class for all pylcddc related exceptions

    Inherits all behaviour from base class ``Exception``.
    """
    pass


class ProtocolVersionError(PylcddcError):
    """
    Error class representing a protocol version mismatch between the
    server and client.
    """

    def __init__(self, server_ver: str, client_vers: Sequence[str]):
        """
        Create a new ProtocolVersionError exception

        :param server_ver: server version
        :param client_vers: versions supported by the client
        """
        super().__init__('Server and client version mismatch. '
                         f'Supported versions by client: {client_vers},'
                         f' version advertised by server: {server_ver}')
        self._server_ver = server_ver
        self._client_vers = client_vers

    @property
    def server_ver(self) -> str:
        """
        Obtain the protocol version advertised by the server

        :return: protocol version advertised by the server
        """
        return self._server_ver

    @property
    def client_vers(self) -> Sequence[str]:
        """
        Obtain a sequence of protocol versions supported by the client

        :return: sequence of protocol versions supported by the client
        """
        return self._client_vers


class RequestError(PylcddcError):
    """
    Error class representing an error reported by LCDd when requesting
    that LCDd take a particular action

    i.e. class representing information contained in a LCDd "huh" response
    """

    def __init__(self, request: bytes, error_msg: str):
        """
        Create a new RequestError exception

        :param request: request that led to the error
        :param error_msg: error message from LCDd
        """
        self._request = request
        self._error_msg = error_msg

    @property
    def error_msg(self) -> str:
        """
        Obtain the error message reported by LCDd

        :return: error message reported by LCDd
        """
        return self._error_msg

    @property
    def request(self) -> bytes:
        """
        Obtain the encoded request that led to the error

        :return: encoded request
        """
        return self._request


class FatalError(PylcddcError):
    """
    Fatal exception for pylcddc library calls.

    Applications should attempt to ``close()`` the connection to LCDd through
    the client object when this happens, and should not make any further
    calls on the client object.
    """

    def __init__(self, why: Exception):
        """
        Instantiate a new ``FatalError`` instance

        :param why: the exception that led to this error
        """
        self._why = why

    @property
    def why(self) -> Exception:
        """
        Return the exception that led to the ``FatalError``
        raised by the library.

        :return: causing exception
        """
        return self._why
