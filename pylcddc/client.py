"""
client.py

Python module used to represent a client connection to a LCDd server.

This module contains:
    - Implementation of a LCDd client, that delegates transmission and
      receiving of LCDd messages to another thread.
    - The client is capable of sending and receiving messages, and
      also handles both the initialization and teardown sequences.
    - Drawing operations and widget operations are delegated to
      screen objects, which live in their own separate module. The client
      only allows the creation and destruction of new screens, but
      does not play an active part in managing widgets.

Copyright Shenghao Yang, 2018

See LICENSE.txt for more details.
"""
import queue
import socket
import time
import typing
from collections.abc import Mapping

from . import commands
from . import exceptions
from . import responses
from . import screen
from .iothread import IOThread

supported_protocol_versions = ('0.3',)  # supported LCDd protocol versions


class Client(Mapping):
    """
    Object representing a LCDd client.

    The client manages screens sent to / from LCDd and provides
    information regarding the display connected to LCDd.
    """
    def __init__(self, host: str = 'localhost', port: int = 13666,
                 timeout: typing.Union[None, float] = 1,
                 max_nonblock_operations: int = 32):
        """
        Create a new LCDd client, connecting to a particular host:port
        combination

        :param host: host to connect to
        :param port: port to connect to
        :param timeout: timeout for client operations.
                        this sets the timeout for operations, such as:
                        connecting, creating screens, deleting screens,
                        and updating screens.
        :param max_nonblock_operations: maximum number of non-blocking screen
                                        operations that can be in flight at any
                                        one time.
        :raises FatalError: on failure to setup the connection subsystem
                            and have it connect to LCDd
        :raises ValueError: on invalid arguments
        """
        self._closed = True
        self._good = False
        self._timeout = timeout
        self._serv_info_resp = None
        self._screen_id_cnt = 0
        self._screens = dict()
        self._screen_ids = dict()
        self._max_nonblock_operations = max_nonblock_operations
        # Starts from 1 because 0x00 is a key reserved by the IO thread
        self._nonblock_operation_keys = list(
            range(1, max_nonblock_operations + 1))

        start_time = time.monotonic()
        try:
            self._socket = socket.create_connection((host, port), timeout)
            self._closed = False

            time_spent = (time.monotonic() - start_time)
            if timeout is not None:
                timeout = max(timeout - time_spent, 0)

            self._iothread = IOThread(self._socket,
                                      self._async_response_handler)
            resp = self._request(
                commands.CommandGenerator.generate_init_command(), timeout)
            if not isinstance(resp, responses.ServInfoResponse):
                raise IOError('Invalid init request response')
        except Exception as e:
            raise exceptions.FatalError(e)

        self._serv_info_resp = resp
        self._good = True

    def __enter__(self):
        """
        To support using the `with` statement.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        To support using the `with` statement.
        """
        self.close()

    def __bool__(self) -> bool:
        """
        Check if the connection between the client and LCDd is in a good state

        A good state means that further requests can be sent between the
        client and LCDd.

        :return: state of the connection between the client and LCDd
        """
        return self._good and (not self._closed)

    def __getitem__(self, name: str) -> screen.Screen:
        """
        Obtain a screen provided by this client to LCDd

        :param name: name of the screen
        :return: screen object
        :raises KeyError: on invalid screen name
        """
        return self._screens[name]

    def __iter__(self) -> typing.Iterator[str]:
        """
        Obtain an iterator iterating through the names of screens
        provided by this client to LCDd.

        :return: screen name iterator
        """
        return iter(self._screens)

    def __len__(self) -> int:
        """
        Obtain the number of screens provided by this client to LCDd.

        :return: screen number.
        """
        return len(self._screens)

    def _async_response_handler(self, response: responses.BaseResponse):
        """
        Response handler for asynchronous responses that can come from
        LCDd.

        :param response: asynchronous response from LCDd.
        :return: None.
        """
        pass

    def _request(self, msg: bytes, timeout: typing.Union[float, None] = 1) \
            -> responses.BaseResponse:
        """
        Send a request to LCDd.

        :param msg: request to send to LCDd.
        :param timeout: timeout value, see ``socket.settimeout()``.
        :return: response object representing the response from LCDd.

        :raises FatalError: on fatal internal error, or operation timing out.
                            both situations are fatal as we have
                            lost synchronization with the background I/O
                            thread.
        """
        return self._request_multiple((msg,), timeout)[0]

    def _request_multiple(
            self, msgs: typing.Sequence[bytes],
            timeout: typing.Union[float, None] = 1) \
            -> typing.Sequence[responses.BaseResponse]:
        """
        Send multiple requests to LCDd.

        :param msgs: requests to send to LCDd.
        :param timeout: timeout value, see ``socket.settimeout()``.
        :return: response objects representing the response from LCDd.

        :raises FatalError: on fatal internal error, or operation timing out.
                            both situations are fatal as we have
                            lost synchronization with the background I/O
                            thread.
        """
        try:
            return self._iothread.request_multiple(msgs, timeout)
        except Exception:
            self._good = False
            raise

    def _request_multiple_nonblock(self, msgs: typing.Sequence[bytes],
                                   key: typing.Any) -> None:
        """
        Send multiple non-blocking requests to LCDd.

        :param msgs: requests to send to LCDd.
        :param key: object used to identify this set of requests.

        :raises FatalError: on fatal internal error.
        """
        try:
            self._iothread.request_multiple_nonblock(key, msgs)
        except Exception:
            self._good = False
            raise

    @property
    def closed(self) -> bool:
        """
        Check if the connection between LCDd and the client is open.

        :return: connection status.

        .. note::
            an open connection doesn't mean the connection is in a good
            state
        """
        return self._closed

    @property
    def nonblock_update_signaling_fileno(self) -> int:
        """
        Obtain the file descriptor that represents the socket that can be
        watched for replies from LCDd regarding nonblocking screen update
        requests.

        Once replies have been detected, i.e. this socket can be read without
        blocking, you can call the ``update_screen_nonblock_finalize()`` method
        to complete the request.

        :return: file descriptor linked to the notification socket.

        .. note::
            Not valid once ``close()`` has been called.
        """
        return self._iothread.event_fileno

    @property
    def server_information_response(self) \
            -> typing.Union[None, responses.ServInfoResponse]:
        """
        Obtain the response returned by the server during the initialization
        process.

        The response contains server information, as well as information
        on the display served up by the server.

        :return: server information response.
        """
        return self._serv_info_resp

    def add_screen(self, s: screen.Screen):
        """
        Add a new screen to the client.

        This operation is always blocking. If there are pending screen update
        operations that have not completed, this method must not be called.

        :param s: screen to add.
        :raises KeyError: If there is already another screen with the same
                          name attached to this client.
        :raises RuntimeError: If there are pending non-blocking screen
                              update operations that have not completed.
        :raises RequestError: If there was a non-fatal error while creating
                              the new screen.
                              The library automatically attempts to recover
                              from this error by deleting the screen after
                              encountering this error.
                              If the screen deletion fails, a ``FatalError``
                              exception is raised, containing a RequestError
                              that led to the attempted error recovery,
                              which resulted in failure.
        :raises FatalError: if there was a fatal error creating the new screen,
                            requiring a re-instantiation of the LCDd connection.
        """
        if (self._max_nonblock_operations
                != len(self._nonblock_operation_keys)):
            raise RuntimeError('Pending non-blocking screen updates')

        if s.name in self:
            raise KeyError(f'screen name {s.name} is not unique')

        candidate_id = self._screen_id_cnt + 1
        request_error_request = None
        request_error_reason = None
        add_requests = s.init_all(candidate_id)
        replies = self._request_multiple(add_requests, self._timeout)

        for i, response in enumerate(replies):
            if isinstance(response, responses.ErrorResponse):
                request_error_request = add_requests[i]
                request_error_reason = response.reason
                break

        if request_error_reason is not None:
            response = self._request(s.destroy_all_atomic(candidate_id),
                                     self._timeout)
            if isinstance(response, responses.ErrorResponse):
                if 'Unknown screen id' not in response:
                    raise exceptions.FatalError(
                        RuntimeError('Inconsistent state: unable to revert '
                                     'changes on screen add error'))
            raise exceptions.RequestError(request_error_request,
                                          request_error_reason)

        else:
            self._screen_id_cnt += 1
            self._screen_ids[s.name] = candidate_id
            self._screens[s.name] = s

    def update_screens(self, screens: typing.Sequence[screen.Screen],
                       blocking: bool = True) -> typing.Union[int, None]:
        """
        Update a number of screens, at once,
        updating the widgets on the screens as well as the screen's attributes.

        ``update_screen_nonblock_finalize()`` must be called to finalize
        processing a non-blocking update requests. No blocking screen-related
        calls can be made until the finalize method returns status objects
        for ALL non-blocking operations.

        :param screens: screens to update
        :param blocking: whether the update is blocking
        :return: key used to track status of request when the client was
                 created in non-blocking mode, else ``None``.
        :raises KeyError: if the screen was never added to the
                          client for display on the server's screen at all.
        :raises IndexError: if there are too many non-blocking update
                            operations in flight.
                            Only raised in non-blocking mode.
        :raises RequestError: if there was a non-fatal error while updating
                              the screen.
                              If multiple screens are updated at once, only
                              the first non-fatal error is raised.
                              The screen may be in a inconsistent state,
                              but all widgets and elements will be present
                              on the screen.
                              Only their attributes and the screen's
                              attributes may be inconsistent.
                              Users can attempt to update the screen's state
                              again.
                              Only returned in blocking mode.
        :raises FatalError: if there was a fatal error updating the screen,
                            requiring a re-instantiation of the LCDd connection
        """
        update_requests = []
        for s in screens:
            update_requests.extend(s.update_all(self._screen_ids[s.name]))

        if not blocking:
            key = self._nonblock_operation_keys.pop()
            self._request_multiple_nonblock(update_requests, key)
            return key
        else:
            replies = self._request_multiple(update_requests, self._timeout)
            for i, reply in enumerate(replies):
                if isinstance(reply, responses.ErrorResponse):
                    raise exceptions.RequestError(update_requests[i],
                                                  reply.reason)

    def update_screen_nonblock_reply_count(self) -> int:
        """
        Obtain the count of non-blocking screen update operations that have
        replies from LCDd.

        :return: reply count.

        .. note::

            Since the storage for replies is a Queue object, the
            count value may not be exact. Use this value with caution.
            If in doubt, refer to ``update_screen_nonblock_completed``
            to confirm that there are no more pending operations to complete.
        """
        return self._iothread.response_nonblock_received_cnt()

    def update_screen_nonblock_reply(
            self, timeout: typing.Union[float, None] = 0) -> bool:
        """
        Check / wait to see if at least one non-blocking screen update
        operation has a reply from LCDd.

        :param timeout: timeout to wait, if no replies have been received yet.
                        See ``selectors`` for information on timeout settings.
        :return: ``True`` if replies are in, ``False`` otherwise.
        :raises exceptions.FatalError: on fatal polling error.

        .. note::

            Cannot be called once ``close()`` has been called.
        """
        try:
            return self._iothread.response_nonblock_received(timeout)
        except Exception as e:
            raise exceptions.FatalError(e)

    def update_screen_nonblock_finalize(
            self, timeout: typing.Union[float, None] = 0) \
            -> typing.Mapping[int, typing.Union[str, None]]:
        """
        Finalize and obtain the errors of non-blocking screen update operations,
        for operations that do have replies from LCDd.

        :param timeout: time to wait for a reply from LCDd sufficient to
                        finalize one request, if insufficient reply data is
                        present. See ``selectors`` for information on timeout
                        settings.
        :return: mapping of non-blocking update keys to error descriptions.
                 An error description of ``None`` means no error occured.
                 Otherwise, an error description is the string returned
                 by LCDd on an update operation error.
        :raises queue.Empty: if no responses have been acquired yet.
        :raises exceptions.FatalError: on I/O thread communication exception.

        .. note::

            Cannot be called once ``close()`` has been called.
        """
        self.update_screen_nonblock_reply(timeout)
        replies = []
        try:
            replies.append(self._iothread.response_nonblock())
        except queue.Empty:
            pass
        rtn = {}
        for reply in replies:
            for response in reply.responses:
                if isinstance(response, responses.ErrorResponse):
                    rtn[reply.key] = response.reason
                    break
            else:
                rtn[reply.key] = None

            self._nonblock_operation_keys.append(reply.key)
        return rtn

    def delete_screen(self, s: screen.Screen):
        """
        Delete a screen, removing that screen from LCDd.

        This operation is always blocking. If there are pending screen update
        operations that have not completed, this method must not be called.

        :param s: screen to delete
        :raises KeyError: if the screen was never added to the client for
                          display on the server's screen at all.
        :raises RuntimeError: If there are pending non-blocking screen
                              update operations that have not completed.
        :raises RequestError: if there was a non-fatal error while removing
                              the screen.
                              Since the screen deletion action is atomic,
                              the screen will simply be present on the
                              display. The application needs to decide
                              whether to retry the procedure, or simply
                              re-instantiate the connection.
        :raises FatalError: if there was a fatal error removing the screen,
                            requiring a re-instantiation of the LCDd connection.
        """
        if (self._max_nonblock_operations
                != len(self._nonblock_operation_keys)):
            raise RuntimeError('Pending non-blocking screen updates')

        req = s.destroy_all_atomic(self._screen_ids[s.name])
        response = self._request(req, self._timeout)
        if isinstance(response, responses.ErrorResponse):
            raise exceptions.RequestError(req, response.reason)

        del self._screen_ids[s.name]
        del self._screens[s.name]

    def close(self):
        """
        Close the connection to LCDd.

        Before closing the connection, it attempts to:
            - Gracefully shutdown the background I/O thread
            - Release the resources associated with the background thread

        - If the background I/O thread fails to shutdown, or resources cannot
          be properly deallocated, an ``OSError`` is raised.

        It also attempts to perform a graceful shutdown of the LCDd socket
        first, before closing it. If the shutdown is not successful,
        the exception is masked and the socket simply closed. However, if
        the socket cannot be closed, an ``OSError`` is raised as well.

        :return: None
        :raises OSError: if there was an error closing the connection to
                         LCDd
        """
        self._iothread.join()
        self._iothread.close()
        if not self._closed:
            self._good = False
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                # ignore - shutting down is a courtesy
                pass
            finally:
                self._socket.close()
            self._closed = True
