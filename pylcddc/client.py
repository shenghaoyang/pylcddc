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

See LICENSE.txt.txt for more details.
"""
import queue
import selectors
import socket
import struct
import threading
import time
import typing
from collections.abc import Mapping

from . import commands
from . import exceptions
from . import responses
from . import screen


class IOThread(threading.Thread):
    """
    I/O thread used to communicate with LCDd.

    The I/O thread receives queued transmissions from the client, and
    dispatches them to LCDd.

    For synchronous messages:
       - A socket is used as a signalling mechanism for notifying the
         I/O thread that the client has information to send.
       - The socket is also used to signal to the client that a response
         for the client's synchronous message has arrived.
       - One queue is used to contain the requests destined for LCDd,
         and another is used to contain the responses received.

    It uses selectors on the I/O file descriptors to avoid putting the
    system into a busy wait loop.

    For asynchronous messages:
        - The I/O thread calls a specified callback function / method
          passed to it, to notify the client about asynchronous
          error conditions / others.

    Thread exit is used to signal to the client that the communications
    channel with LCDd may be corrupted. It may occur in the following cases:
        - Failure to communicate over the LCDd socket.
        - Failure to communicate over the client socket.
        - Failure to communicate over inter-thread queues.
        - Failure to execute callback for asynchronous messages.

    On thread exit:
        - The thread side of the communication socket-pair is closed, to notify
          the waiting user thread if the user thread was blocked.
        - The thread stop condition variable is set.
    """

    def __init__(self, lcdd_socket: socket.SocketType,
                 async_callback: typing.Callable[
                     [responses.BaseResponse], None],
                 max_queued_requests: int = 0x100):
        """
        Create a new LCDd I/O thread, and run it.

        :param lcdd_socket: socket used for communication with the
                            LCDd
        :param async_callback: callback used to process asynchronous responses
                               from LCDd.
                               This callback is called in the IOThread's
                               context, Users are advised to keep their
                               callbacks short. No requests can be made to LCDd
                               within the callback.
        :param max_queued_requests: maximum number of requests that can
                                    be queued to the thread at once.
        :raises OSError: on inability to initialize the I/O thread
        """
        super().__init__(name='pylcddc I/O thread')

        self._lcdd_socket = lcdd_socket
        self._async_callback = async_callback
        self._closed = False
        self._max_queued_requests = max_queued_requests

        # AF_UNIX for reliable datagram sockets, as opposed to AF_INET
        # SOCK_SEQPACKET guarantees reliability, but Windows will probably
        # never support it. At least Windows is starting to support AF_UNIX.
        self._signalling_sockets = socket.socketpair(family=socket.AF_UNIX,
                                                     type=socket.SOCK_SEQPACKET)
        self._signal_socket = self._signalling_sockets[0]
        self._client_signal_socket = self._signalling_sockets[1]

        self._transmit_queue = queue.Queue(self.max_queued_requests)
        self._receive_queue = queue.Queue(self.max_queued_requests)

        self._stop_thread = threading.Event()
        self._thread_death_exception = None

        self.start()

    @property
    def max_queued_requests(self) -> int:
        return self._max_queued_requests

    def request_multiple(self, msgs: typing.Sequence[bytes],
                         timeout: typing.Union[float, None] = 1) \
            -> typing.Sequence[responses.BaseResponse]:
        """
        Send multiple requests to LCDd

        :param msgs: requests to send to LCDd.
        :param timeout: timeout value, see ``socket.settimeout()``.
        :return: response objects representing the response from LCDd
        :raises FatalError: on operation timeout or communication error.

        .. note::
            On fatal exceptions, the I/O Thread is stopped. The user needs to
            call ``close()`` on the I/O thread to release its
            resources.
        """
        try:
            if not self.is_alive():
                raise IOError('I/O thread terminated')

            try:
                for msg in msgs:
                    self._transmit_queue.put(msg, False)
            except queue.Full:
                raise IOError('Unable to enqueue request for transmission')

            try:
                # Send I/O thread timeout, num of messages, and timeout validity
                self._client_signal_socket.sendall(
                    struct.pack('@Nd?', len(msgs),
                                timeout if timeout is not None else 0,
                                True if timeout is not None else False))
                # timeout handled by thread - on timeout, IO thread shuts down
                # socket, so we'll get notified too.
                buf = self._client_signal_socket.recv(struct.calcsize('@N'))
                # Check for empty response
                if not buf:
                    raise IOError('I/O thread terminated')
                replies = struct.unpack('@N', buf)[0]
                if replies != len(msgs):
                    raise RuntimeError('I/O thread dispatched mismatched number'
                                       ' of requests')
            except socket.timeout:
                raise TimeoutError('Timeout in I/O thread communication')

            try:
                response_objects = [self._receive_queue.get(False)
                                    for __ in range(replies)]
            except queue.Empty:
                raise IOError('Insufficient elements in receive queue')

        except Exception as e:
            self.join()
            raise exceptions.FatalError(e)

        return response_objects

    def request(self, msg: bytes,
                timeout: typing.Union[float, None] = 1) -> responses.BaseResponse:
        """
        Send a single request to LCDd

        :param msg: request to send to LCDd
        :param timeout: timeout value, see ``socket.settimeout()``.
        :return: response object representing the response from LCDd

        :raises FatalError: on error communicating with IOThread or timeout

        .. note::
            On fatal exceptions, the I/O Thread is stopped. The user needs to
            call ``close()`` on the I/O thread to release its resources.
        """
        try:
            if not self.is_alive():
                raise IOError('I/O thread terminated')

            try:
                self._transmit_queue.put(msg, False)
            except queue.Full:
                raise IOError('Transmit queue full')

            try:
                self._client_signal_socket.sendall(
                    struct.pack('@Nd?', 1,
                                timeout if timeout is not None else 0.00,
                                True if timeout is not None else False))
                self._client_signal_socket.settimeout(timeout)
                buf = self._client_signal_socket.recv(struct.calcsize('@N'))
                if not buf:
                    raise IOError('I/O thread terminated')
                replies = struct.unpack('@N', buf)[0]
                if replies != 1:
                    raise RuntimeError('I/O thread dispatched mismatched '
                                       'number of requests')
            except socket.timeout:
                raise TimeoutError('Timeout in I/O thread communication')

            try:
                res = self._receive_queue.get(False)
            except queue.Empty:
                raise IOError('Insufficient elements in receive queue')

        except Exception as e:
            self.join()
            raise exceptions.FatalError(e)

        return res

    def join(self, timeout: typing.Optional[typing.Union[None, float]] = None) \
            -> None:
        """
        Wait until the thread terminates.

        This function simply sets the stop flag of the thread and then
        calls the superclass implementation of ``join()``

        See the documentation of ``threading.Thread.join()`` for more details.

        Thread termination does not release the resources the thread has.
        Users need to manually release the thread-allocated system resources
        by calling ``close()``

        :param timeout: timeout for the wait operation
        :return: None
        """
        self._stop_thread.set()
        return super().join(timeout)

    def close(self):
        """
        Clean up resources associated allocated by IOThread

        Multiple calls to this method are alright.

        :return: None
        :raises RuntimeError: if called when IOThread is still running
        :raises OSError: on cleanup error
        """
        if self.is_alive():
            raise RuntimeError('close called when IOThread is still running')
        if self._closed:
            if hasattr(self, '_signalling_sockets'):
                map(lambda s: s.close(), self._signalling_sockets)
            self._closed = True
        else:
            return

    def start(self):
        """
        Start the LCDd I/O thread

        See the documentation for ``threading.Thread.start()`` for more details

        :raises RuntimeError: if called more than once on the same thread
        :raises RuntimeError: if called after the IOThread has been closed
        :raises RuntimeError: if called after the IOThread has been stopped
        """
        if self._stop_thread.is_set():
            raise RuntimeError('attempted to start IOThread after it has'
                               ' been requested to stop')
        if self._closed:
            raise RuntimeError('attempted to start IOthread after it has '
                               ' been closed')
        super().start()

    def run(self) -> None:
        """
        Entry point for the I/O thread.

        Any exception thrown in the thread terminates it.

        :return: None
        """
        # buffer used to buffer incoming information
        lcdd_buffer = bytearray()
        requests_dispatched = 0
        pending_synchronous_replies = 0

        try:
            def send_request():
                nonlocal requests_dispatched, pending_synchronous_replies
                self._signal_socket.settimeout(0)
                buf = self._signal_socket.recv(struct.calcsize('@Nd?'))
                if not buf:
                    raise IOError('Client request length read error')

                num_requests, timeout, block = struct.unpack('@Nd?', buf)
                requests = bytearray()

                for __ in range(num_requests):
                    request_bytes = self._transmit_queue.get(False)
                    requests.extend(request_bytes)

                self._lcdd_socket.settimeout(None if block else timeout)
                self._lcdd_socket.sendall(requests)
                requests_dispatched = num_requests
                pending_synchronous_replies = num_requests

            def handle_incoming_responses():
                nonlocal requests_dispatched, pending_synchronous_replies

                self._lcdd_socket.settimeout(0)
                buf = self._lcdd_socket.recv(responses.MAX_RESPONSE_LENGTH
                                             * self.max_queued_requests)
                if not buf:
                    raise IOError('LCDd terminated connection')
                lcdd_buffer.extend(buf)
                if len(lcdd_buffer) > (responses.MAX_RESPONSE_LENGTH
                                       * self.max_queued_requests):
                    raise IOError('RX buffer limit reached - no valid response')

                res = lcdd_buffer.splitlines(True)
                for r in res:
                    robj = responses.parse_response(r.decode('utf-8'))
                    if (robj.response_attributes
                            & responses.ResponseAttribute.ASYNCHRONOUS):
                        self._async_callback(robj)
                    else:
                        self._receive_queue.put(robj, False)
                        pending_synchronous_replies -= 1

                if (not pending_synchronous_replies) and requests_dispatched:
                    self._signal_socket.settimeout(0)
                    self._signal_socket.sendall(
                        struct.pack('@N', requests_dispatched))
                    requests_dispatched = 0

                lcdd_buffer.clear()
                if not r.endswith(b'\n'):
                    # ignore the error about r being possibly undefined.
                    # the socket is ready for read when this function is
                    # called, so there is either data to be placed into
                    # r after the buffer has been extended, or, no data
                    # but an exceptional condition on the socket, which
                    # will cause an exception to be raised before the
                    # thread continues to this state, and hence, r will
                    # never be used in a situation where it its undefined.
                    lcdd_buffer.extend(r)

            with selectors.DefaultSelector() as selector:
                selector.register(self._signal_socket, selectors.EVENT_READ,
                                  send_request)
                selector.register(self._lcdd_socket, selectors.EVENT_READ,
                                  handle_incoming_responses)
                while not self._stop_thread.is_set():
                    ready = selector.select(0.1)
                    for key, event in ready:
                        key.data()

        except Exception as e:
            self._thread_death_exception = e
        finally:
            self._stop_thread.set()
            self._signal_socket.shutdown(socket.SHUT_RDWR)


supported_protocol_versions = ('0.3',)  # supported LCDd protocol versions


class Client(Mapping):
    """
    Object representing a LCDd client.

    The client manages screens sent to / from LCDd and provides
    information regarding the display connected to LCDd.
    """

    def __init__(self, host: str = 'localhost', port: int = 13666,
                 timeout: typing.Union[None, float] = 1,
                 max_queued_requests: int = 0x1000):
        """
        Create a new LCDd client, connecting to a particular host:port
        combination

        :param host: host to connect to
        :param port: port to connect to
        :param timeout: timeout for client operations.
                        this sets the timeout for operations, such as:
                        connecting, creating screens, deleting screens,
                        and updating screens.
        :param max_queued_requests: maximum number of batched requests
                                    sent to the I/O handler thread at once.
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

        start_time = time.monotonic()
        try:
            self._socket = socket.create_connection((host, port), timeout)
            self._closed = False

            time_spent = (time.monotonic() - start_time)
            if timeout is not None:
                timeout = max(timeout - time_spent, 0)

            self._iothread = IOThread(self._socket,
                                      self._async_response_handler,
                                      max_queued_requests)
            resp = self._request(
                commands.CommandGenerator.generate_init_command(), timeout)
            if not isinstance(resp, responses.ServInfoResponse):
                raise IOError('Invalid init request response')
        except Exception as e:
            raise exceptions.FatalError(e)

        self._serv_info_resp = resp
        self._good = True

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
        try:
            return self._iothread.request(msg, timeout)
        except Exception as e:
            self._good = False
            raise exceptions.FatalError(e)

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
        replies = list()
        try:
            # Split messages into batches according to the maximum
            # number of messages that can be sent to the iothread at once
            batch_size = self._iothread.max_queued_requests
            for start in range((len(msgs) // self._iothread.max_queued_requests)
                               + 1 if (len(msgs)
                                       % self._iothread.max_queued_requests)
                               else 0):
                batch = msgs[start * batch_size:
                             (start * batch_size) + batch_size]
                replies.extend(self._iothread.request_multiple(batch, timeout))
        except Exception as e:
            self._good = False
            raise exceptions.FatalError(e)

        return replies

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
    def server_information_response(self) \
            -> typing.Union[None, responses.ServInfoResponse]:
        """
        Obtain the response returned by the server during the initialization
        process.

        The response contains server information, as well as information
        on the display served up by the server.

        :return: server information response, may be ``None`` if
                 no response was acquired (if the client encountered an
                 error connecting to the server)
        """
        return self._serv_info_resp

    def add_screen(self, s: screen.Screen, use_multi_req: bool = False):
        """
        Add a new screen to the client

        Asynchronous messages from LCDd are ignored while sending screen
        add messages.

        :param s: screen to add.
        :param use_multi_req: use experimental request batching,
                              defaults to ``False``.
        :raises KeyError: If there is already another screen with the same
                          name attached to this client.
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
        if s.name in self:
            raise KeyError(f'screen name {s.name} is not unique')

        candidate_id = self._screen_id_cnt + 1
        add_success = False
        request_error_request = None
        request_error_reason = None

        add_requests = s.init_all(candidate_id)
        if not use_multi_req:
            for req in add_requests:
                response = self._request(req, self._timeout)
                if isinstance(response, responses.ErrorResponse):
                    request_error_request = req
                    request_error_reason = response.reason
                    break
            else:
                add_success = True
        else:
            replies = self._request_multiple(add_requests, self._timeout)
            for i, response in enumerate(replies):
                if isinstance(response, responses.ErrorResponse):
                    request_error_request = add_requests[i]
                    request_error_reason = response.reason
                    break
            else:
                add_success = True

        if not add_success:
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

    def update_screen(self, s: screen.Screen, use_multi_req: bool = False):
        """
        Update a screen, updating the widgets on the screen as well as
        the screen's attributes.

        Asynchronous LCDd messages are ignored while updating screen attributes.

        :param s: screen to update
        :param use_multi_req: use experimental request batching,
                              ``False`` by default
        :raises KeyError: if the screen was never added to the
                          client for display on the server's screen at all.
        :raises RequestError: if there was a non-fatal error while updating
                              the screen.
                              The screen may be in a inconsistent state,
                              but all widgets and elements will be present
                              on the screen.
                              Only their attributes and the screen's
                              attributes may be inconsistent.
                              Users can attempt to update the screen's state
                              again.
        :raises FatalError: if there was a fatal error updating the screen,
                         requiring a re-instantiation of the LCDd connection
        """
        update_requests = s.update_all(self._screen_ids[s.name])
        if not use_multi_req:
            for req in update_requests:
                response = self._request(req, self._timeout)
                if isinstance(response, responses.ErrorResponse):
                    raise exceptions.RequestError(req, response.reason)
        else:
            replies = self._request_multiple(update_requests, self._timeout)
            for i, reply in enumerate(replies):
                if isinstance(reply, responses.ErrorResponse):
                    raise exceptions.RequestError(update_requests[i],
                                                  reply.reason)

    def delete_screen(self, s: screen.Screen):
        """
        Delete a screen, removing that screen from LCDd.

        Asynchronous LCDd messages are ignored when sending screen delete
        messages.

        :param s: screen to delete
        :raises KeyError: if the screen was never added to the client for
                          display on the server's screen at all.
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
