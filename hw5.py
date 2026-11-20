"""
Where solution code to HW5 should be written.  No other files should
be modified.
"""

import socket
import io
import time
import typing
import struct
import homework5
import homework5.logging

# packet format - 4-byte big-endian sequence number followed by the payload
# an ACK is just 4 bytes: the next sequence number the receiver expects
# the last data packet has an empty payload and acts as the FIN.
HEADER = 4
CHUNK = homework5.MAX_PACKET - HEADER


def send(sock: socket.socket, data: bytes):
    """
    Implementation of the sending logic for sending data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.
        data -- A bytes object, containing the data to send over the network.
    """

    # Naive implementation where we chunk the data to be sent into
    # packets as large as the network will allow, and then send them
    # over the network, pausing half a second between sends to let the
    # network "rest" :)

    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    chunks.append(b"")  # empty payload = FIN
    est = dev = None
    rto = 1.0

    for seq, chunk in enumerate(chunks):
        pkt = struct.pack("!I", seq) + chunk
        is_fin = seq == len(chunks) - 1
        resent = False
        tries = 0
        while True:
            start = time.time()
            sock.send(pkt)
            acked = False
            while not acked:
                left = start + rto - time.time()
                if left <= 0:
                    break
                sock.settimeout(left)
                try:
                    acked = struct.unpack("!I", sock.recv(homework5.MAX_PACKET)[:HEADER])[0] > seq
                except socket.timeout:
                    break
            if acked:
                break
            # timeout, back off and retransmit
            # the receiver may already have exited after the FIN
            # so give up on the FIN after a few tries

            tries += 1
            if is_fin and tries == 5:
                return
            rto *= 2
            resent = True

        # update the RTT estimate
        if not resent:
            rtt = time.time() - start
            if est is None:
                est, dev = rtt, rtt / 2
            else:
                dev = 0.75 * dev + 0.25 * abs(rtt - est)
                est = 0.875 * est + 0.125 * rtt
            rto = max(est + 4 * dev, 0.05)


def recv(sock: socket.socket, dest: io.BufferedIOBase) -> int:
    """
    Implementation of the receiving logic for receiving data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.

    Return:
        The number of bytes written to the destination.
    """

    # Naive solution, where we continually read data off the socket
    # until we don't receive any more data, and then return.

    expected = 0
    num_bytes = 0
    while True:
        data = sock.recv(homework5.MAX_PACKET)
        if struct.unpack("!I", data[:HEADER])[0] == expected:
            if len(data) == HEADER:  # FIN
                break
            dest.write(data[HEADER:])
            dest.flush()
            num_bytes += len(data) - HEADER
            expected += 1
        sock.send(struct.pack("!I", expected))

    # ACK the FIN, then linger briefly to re-ACK it if the sender retransmits
    # because our ACK was lost
    fin_ack = struct.pack("!I", expected + 1)
    sock.send(fin_ack)
    sock.settimeout(2)
    try:
        while True:
            sock.recv(homework5.MAX_PACKET)
            sock.send(fin_ack)
    except socket.timeout:
        pass
    return num_bytes
