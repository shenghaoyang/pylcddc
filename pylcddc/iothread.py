"""
iothread.py

Python module used to contain a class that allows transmission of messages to
LCDd in another thread, that does not block the main thread while it is
performing I/O

Copyright Shenghao Yang, 2018

See LICENSE.txt for more details.
"""
import copy
import queue
import resource
import selectors
import socket
import threading
import typing
from collections import namedtuple

from . import exceptions
from . import responses


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
    IOThreadRequest = namedtuple('IOThreadRequest', ('requests', 'timeout', 'key'))
    IOThreadReply = namedtuple('IOThreadReply', ('responses', 'key'))

    def __init__(self, lcdd_socket: socket.SocketType,
                 async_callback: typing.Callable[
                     [responses.BaseResponse], None]):
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
        :raises OSError: on inability to initialize the I/O thread
        """
        super().__init__(name='pylcddc I/O thread')

        self._lcdd_socket = lcdd_socket
        self._async_callback = async_callback
        self._closed = False
        self._bufsize = resource.getpagesize()
        self._signalling_selector = selectors.DefaultSelector()

        # AF_UNIX for reliable datagram sockets, as opposed to AF_INET
        # SOCK_SEQPACKET guarantees reliability, but Windows will probably
        # never support it. At least Windows is starting to support AF_UNIX.
        try:
            self._signalling_sockets = socket.socketpair(
                family=socket.AF_UNIX, type=socket.SOCK_SEQPACKET)
        except OSError:
            self._signalling_sockets = socket.socketpair(
                family=socket.AF_UNIX, type=socket.SOCK_STREAM)
        self._signal_socket = self._signalling_sockets[0]
        self._client_signal_socket = self._signalling_sockets[1]
        self._signalling_selector.register(self._client_signal_socket,
                                           selectors.EVENT_READ)

        self._transmit_queue = queue.Queue()
        self._receive_queue = queue.Queue()

        self._stop_thread = threading.Event()
        self._thread_death_exception = None

        self.start()

    @property
    def event_fileno(self) -> int:
        """
        Obtain the file descriptor that represents the socket that can be
        watched for asynchronous request completion.

        Once request completion has been detected, i.e. this socket can be
        read without blocking, you can call the ``responses_nonblock()`` method
        to obtain the response objects.

        :return: file descriptor linked to the notification socket.

        .. note::
            Not valid once the IOThread has been closed.
        """
        return self._client_signal_socket.fileno()

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

            self._transmit_queue.put(
                self.IOThreadRequest(msgs, timeout, 0x00), False)

            try:
                self._client_signal_socket.settimeout(0)
                self._client_signal_socket.sendall(b'\x00')
                if not self.response_nonblock_received(timeout):
                    raise TimeoutError('Timeout receiving response')
            except socket.timeout:
                raise TimeoutError('Timeout in I/O thread communication')

            reply = self.response_nonblock()
            if reply.key != 0x00:
                raise RuntimeError('Responses from non-blocking requests '
                                   'not consumed')

        except Exception as e:
            self.join()
            raise exceptions.FatalError(e)

        return reply.responses

    def request_multiple_nonblock(self, key: typing.Any,
                                  msgs: typing.Sequence[bytes]) -> None:
        """
        Send multiple requests to LCDd, but don't block for responses.

        :param key: key used to distinguish requests from one another.
                    key value of 0x00 is reserved for blocking requests.
        :param msgs: requests to send to LCDd.
        :raises FatalError: on operation timeout or communication error.

        .. note::
            If a non-blocking request's responses from LCDd have not been
            consumed, one cannot initiate another blocking request.

        .. note::
            On fatal exceptions, the I/O Thread is stopped. The user needs to
            call ``close()`` on the I/O thread to release its
            resources.
        """
        try:
            if not self.is_alive():
                raise IOError('I/O thread terminated')

            self._transmit_queue.put(
                self.IOThreadRequest(msgs, 0x00, key), False)

            self._client_signal_socket.settimeout(0)
            self._client_signal_socket.sendall(b'\x00')
        except Exception as e:
            self.join()
            raise exceptions.FatalError(e)

    def response_nonblock_received_cnt(self) -> int:
        """
        Obtain the count of non-blocking requests that have received replies.

        :return: fufilled request count.

        .. note::

            Since the storage for request responses is a Queue object, the
            count value may not be exact. Use this value with caution.
            If in doubt, refer to ``response_nonblock_received`` to confirm
            that there are no more pending replies to be read.
        """
        return self._receive_queue.qsize()

    def response_nonblock_received(
            self, timeout: typing.Union[float, None] = 0) -> bool:
        """
        Check / wait to see if at least the set of responses expected for one
        non-blocking request have been received.

        :param timeout: timeout to wait, if no responses have been received yet.
                        See ``selectors`` for information on timeout settings.
        :return: ``True`` if responses have been received, ``False`` otherwise.
        :raises exceptions.FatalError: on fatal polling error.
        """
        try:
            ready = self._signalling_selector.select(timeout)
        except Exception as e:
            raise exceptions.FatalError(e)

        return True if ready else False

    def response_nonblock(self) -> 'IOThread.IOThreadReply':
        """
        Obtain the responses acquired from the earliest
        request that was sent through the non-blocking request function, for
        which the responses have not been obtained yet.

        :return: reply object containing received responses.
        :raises queue.Empty: if no responses have been acquired yet.
        :raises exceptions.FatalError: on thread signal channel I/O error.
        """
        try:
            buf = self._client_signal_socket.recv(0x01)
            if not buf:
                raise RuntimeError('I/O thread terminated')
        except Exception as e:
            raise exceptions.FatalError(e)

        return self._receive_queue.get(False)

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
            self._signalling_selector.close()
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
        rx_buffer = bytearray()
        tx_buffer = bytearray()

        request_servicing = None
        bytes_dispatched = 0
        response_objects = []

        selector = selectors.DefaultSelector()
        selector.register(self._signal_socket, selectors.EVENT_READ)
        selector.register(self._lcdd_socket, selectors.EVENT_READ)
        try:
            def send_request_bytes():
                nonlocal tx_buffer, bytes_dispatched
                self._lcdd_socket.settimeout(0)
                sent = self._lcdd_socket.send(tx_buffer[bytes_dispatched:])
                bytes_dispatched += sent
                if bytes_dispatched == len(tx_buffer):
                    tx_buffer.clear()
                    selector.modify(self._lcdd_socket, selectors.EVENT_READ)

            def get_request():
                nonlocal bytes_dispatched, request_servicing
                nonlocal tx_buffer

                if request_servicing:
                    return

                self._signal_socket.settimeout(0)
                buf = self._signal_socket.recv(0x01)
                if not buf:
                    raise IOError('Signal socket read error')

                request_servicing = self._transmit_queue.get(False)
                tx_buffer.extend(b''.join(request_servicing.requests))
                bytes_dispatched = 0
                selector.modify(self._lcdd_socket,
                                selectors.EVENT_READ | selectors.EVENT_WRITE)

            def handle_incoming_responses():
                nonlocal request_servicing

                self._lcdd_socket.settimeout(0)
                buf = self._lcdd_socket.recv(self._bufsize)
                if not buf:
                    raise IOError('LCDd terminated connection')
                rx_buffer.extend(buf)

                if request_servicing:
                    buffer_limit = (responses.MAX_RESPONSE_LENGTH
                                    * len(request_servicing.requests))
                else:
                    buffer_limit = responses.MAX_RESPONSE_LENGTH

                if len(rx_buffer) > buffer_limit:
                    raise IOError('RX buffer limit reached - no valid response')

                res = rx_buffer.splitlines(True)
                for r in res:
                    robj = responses.parse_response(r.decode('utf-8'))
                    if (robj.response_attributes
                            & responses.ResponseAttribute.ASYNCHRONOUS):
                        self._async_callback(robj)
                    else:
                        response_objects.append(robj)

                if ((request_servicing is not None)
                        and (len(response_objects)
                             == len(request_servicing.requests))):
                    self._receive_queue.put(
                        self.IOThreadReply(copy.copy(response_objects),
                                           request_servicing.key))
                    self._signal_socket.settimeout(0)
                    self._signal_socket.sendall(b'\x00')
                    response_objects.clear()
                    request_servicing = None

                rx_buffer.clear()
                if not r.endswith(b'\n'):
                    # ignore the error about r being possibly undefined.
                    # the socket is ready for read when this function is
                    # called, so there is either data to be placed into
                    # r after the buffer has been extended, or, no data
                    # but an exceptional condition on the socket, which
                    # will cause an exception to be raised before the
                    # thread continues to this state, and hence, r will
                    # never be used in a situation where it its undefined.
                    rx_buffer.extend(r)

            while not self._stop_thread.is_set():
                ready = selector.select(0.1)
                for key, event in ready:
                    if key.fileobj == self._signal_socket:
                        get_request()
                    if key.fileobj == self._lcdd_socket:
                        if event & selectors.EVENT_WRITE:
                            send_request_bytes()
                        if event & selectors.EVENT_READ:
                            handle_incoming_responses()

        except Exception as e:
            self._thread_death_exception = e
        finally:
            selector.close()
            self._stop_thread.set()
            self._signal_socket.shutdown(socket.SHUT_RDWR)
