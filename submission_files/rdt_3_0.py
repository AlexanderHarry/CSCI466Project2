import Network
import argparse
from time import sleep
import hashlib
import time
import  network_3_0


class Packet:
    ## the number of bytes used to store packet length
    seq_num_S_length = 10
    length_S_length = 10
    ## length of md5 checksum in hex
    checksum_length = 32

    def __init__(self, seq_num, msg_S):
        self.seq_num = seq_num
        self.msg_S = msg_S

    @classmethod
    def from_byte_S(self, byte_S):
        if Packet.corrupt(byte_S):
            raise RuntimeError('Cannot initialize Packet: byte_S is corrupt')
        # extract the fields
        seq_num = int(byte_S[Packet.length_S_length: Packet.length_S_length + Packet.seq_num_S_length])
        msg_S = byte_S[Packet.length_S_length + Packet.seq_num_S_length + Packet.checksum_length:]
        return self(seq_num, msg_S)

    def get_byte_S(self):
        # convert sequence number of a byte field of seq_num_S_length bytes
        seq_num_S = str(self.seq_num).zfill(self.seq_num_S_length)
        # convert length to a byte field of length_S_length bytes
        length_S = str(self.length_S_length + len(seq_num_S) + self.checksum_length + len(self.msg_S)).zfill(
            self.length_S_length)
        # compute the checksum
        checksum = hashlib.md5((length_S + seq_num_S + self.msg_S).encode('utf-8'))
        checksum_S = checksum.hexdigest()
        # compile into a string
        return length_S + seq_num_S + checksum_S + self.msg_S

    @staticmethod
    def corrupt(byte_S):
        # extract the fields
        length_S = byte_S[0:Packet.length_S_length]
        seq_num_S = byte_S[Packet.length_S_length: Packet.seq_num_S_length + Packet.seq_num_S_length]
        checksum_S = byte_S[
                     Packet.seq_num_S_length + Packet.seq_num_S_length: Packet.seq_num_S_length + Packet.length_S_length + Packet.checksum_length]
        msg_S = byte_S[Packet.seq_num_S_length + Packet.seq_num_S_length + Packet.checksum_length:]

        # compute the checksum locally
        checksum = hashlib.md5(str(length_S + seq_num_S + msg_S).encode('utf-8'))
        computed_checksum_S = checksum.hexdigest()
        # and check if the same
        return checksum_S != computed_checksum_S


class RDT:
    ## latest sequence number used in a packet
    seq_num = 1
    ## buffer of bytes read from network
    byte_buffer = ''

    def __init__(self, role_S, server_S, port):
        self.network = network_3_0.NetworkLayer(role_S, server_S, port)

    def disconnect(self):
        self.network.disconnect()

    def rdt_1_0_send(self, msg_S):
        p = Packet(self.seq_num, msg_S)
        self.seq_num += 1
        self.network.udt_send(p.get_byte_S())

    def rdt_1_0_receive(self):
        ret_S = None
        byte_S = self.network.udt_receive()
        self.byte_buffer += byte_S
        # keep extracting packets - if reordered, could get more than one
        while True:
            # check if we have received enough bytes
            if (len(self.byte_buffer) < Packet.length_S_length):
                return ret_S  # not enough bytes to read packet length
            # extract length of packet
            length = int(self.byte_buffer[:Packet.length_S_length])
            if len(self.byte_buffer) < length:
                return ret_S  # not enough bytes to read the whole packet
            # create packet from buffer content and add to return string
            p = Packet.from_byte_S(self.byte_buffer[0:length])
            ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
            # remove the packet bytes from the buffer
            self.byte_buffer = self.byte_buffer[length:]
            # if this was the last packet, will return on the next iteration

    def rdt_2_1_send(self, msg_S):
        p = Packet(self.seq_num, msg_S)

        while True:
            self.network.udt_send(p.get_byte_S())  # send packet to other side

            # get response
            response = ''
            # while response is ''
            while response == '':
                response = self.network.udt_receive()
            # length of response
            m_length = int(response[:Packet.length_S_length])
            self.byte_buffer = response[m_length:]  # going through the messege to get byte buffer

            if Packet.corrupt(response[:m_length]):
                self.byte_buffer = ''
                print("Corrupt Packet")
            if not (Packet.corrupt(response[:m_length])):
                # check if we have a messege of '1' for ack and '0' for nak
                rep_packet = Packet.from_byte_S(response[:m_length])

                # check for ACK
                if rep_packet.msg_S == "1":
                    self.seq_num += 1
                    print("Got ACK")
                    break
                # check for NAK
                elif rep_packet.msg_S == "0":
                    self.byte_buffer = ''
                    print("Got NAK, Resend last packet")
                # check for repeat packet

    def rdt_2_1_receive(self):
        ret_S = None
        byte_S = self.network.udt_receive()
        self.byte_buffer += byte_S
        while True:
            if (len(self.byte_buffer) < Packet.length_S_length):
                return ret_S  # not enough bytes to read packet length
                # extract length of packet
            length = int(self.byte_buffer[:Packet.length_S_length])

            if len(self.byte_buffer) < length:
                return ret_S  # not enough bytes to read the whole packet

            if Packet.corrupt(self.byte_buffer):
                # if corrupt NAK
                NAK_packet = Packet(self.seq_num, "0")
                self.network.udt_send(NAK_packet.get_byte_S())
                self.byte_buffer = self.byte_buffer[length:]
                print("Corrupt Packet, Send NAK")
            else:
                # if not corrupt:
                # create packet from buffer content and add to return string
                p = Packet.from_byte_S(self.byte_buffer[0:length])
                # if the seq_num is <= to our current seq_num
                if p.seq_num < self.seq_num:
                    # if duplicate NAK and wait for resond
                    NAK_packet = Packet(self.seq_num, "0")
                    self.network.udt_send(NAK_packet.get_byte_S())
                    self.byte_buffer = self.byte_buffer[length:]
                elif self.seq_num <= p.seq_num:
                    # new packet, ACK and return
                    # ACK
                    ACK_packet = Packet(self.seq_num, "1")
                    self.network.udt_send(ACK_packet.get_byte_S())

                    # returning the string
                    ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
                    # remove the packet bytes from the buffer
                    self.byte_buffer = self.byte_buffer[length:]
                    self.seq_num += 1

            # clearing byte buffer
            self.byte_buffer = self.byte_buffer[length:]
        # returning the resp string
        return ret_S
        # ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
        # remove the packet bytes from the buffer
        # self.byte_buffer = self.byte_buffer[length:]
        # if this was the last packet, will return on the next iteration

    def rdt_3_0_send(self, msg_S):
        p = Packet(self.seq_num, msg_S)
        Time = None

        while True:
            self.network.udt_send(p.get_byte_S())  # send packet to other side
            #get current time
            Time = time.clock()
            # get response
            response = ''
            # while response is ''

            while True:
                if (response != '') or (time.clock() > (Time + 1)):
                    break
                # getting response
                response = self.network.udt_receive()

            if response == '':
                print("Error Timeout")
                continue
                # this keyboard goes to the next cycle of the enclosing loop, done to avoid indent confusion

                # length of response
            m_length = int(response[:Packet.length_S_length])
            # getting byte buffer
            self.byte_buffer = response[m_length:]  # going through the messege to get byte buffer

            if Packet.corrupt(response[:m_length]):
                self.byte_buffer = ''
                print("Corrupt Packet")
            if not (Packet.corrupt(response[:m_length])):
                # check if we have a messege of '1' for ack and '0' for nak
                rep_packet = Packet.from_byte_S(response[:m_length])

                # check for ACK
                if rep_packet.msg_S == "1":
                    self.seq_num += 1
                    print("Got ACK")
                    break
                # check for NAK
                elif rep_packet.msg_S == "0":
                    print("Got NAK, resend last packet")
                    self.byte_buffer = ''
                # check for repeat packet


    def rdt_3_0_receive(self):
        ret_S = None
        byte_S = self.network.udt_receive()
        self.byte_buffer += byte_S
        while True:
            if (len(self.byte_buffer) < Packet.length_S_length):
                return ret_S  # not enough bytes to read packet length
                # extract length of packet
            length = int(self.byte_buffer[:Packet.length_S_length])

            if len(self.byte_buffer) < length:
                return ret_S  # not enough bytes to read the whole packet

            if Packet.corrupt(self.byte_buffer):
                # if corrupt NAK
                NAK_packet = Packet(self.seq_num, "0")
                self.network.udt_send(NAK_packet.get_byte_S())
                self.byte_buffer = self.byte_buffer[length:]
                print("Corrupt Packet, send NAK")
            else:
                # if not corrupt:
                # create packet from buffer content and add to return string
                p = Packet.from_byte_S(self.byte_buffer[0:length])
                # if the seq_num is <= to our current seq_num

                if p.seq_num < self.seq_num:
                    # if duplicate NAK and wait for resond
                    NAK_packet = Packet(self.seq_num, "0")
                    self.network.udt_send(NAK_packet.get_byte_S())
                    self.byte_buffer = self.byte_buffer[length:]
                elif self.seq_num == p.seq_num:
                    # new packet, ACK and return
                    # ACK
                    ACK_packet = Packet(self.seq_num, "1")
                    self.network.udt_send(ACK_packet.get_byte_S())

                    # returning the string
                    ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
                    # remove the packet bytes from the buffer
                    self.byte_buffer = self.byte_buffer[length:]
                    self.seq_num += 1

            # clearing byte buffer
            self.byte_buffer = self.byte_buffer[length:]
        # returning the resp string
        return ret_S


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RDT implementation.')
    parser.add_argument('role', help='Role is either client or server.', choices=['client', 'server'])
    parser.add_argument('server', help='Server.')
    parser.add_argument('port', help='Port.', type=int)
    args = parser.parse_args()

    rdt = RDT(args.role, args.server, args.port)
    if args.role == 'client':
        rdt.rdt_1_0_send('MSG_FROM_CLIENT')
        sleep(2)
        print(rdt.rdt_1_0_receive())
        rdt.disconnect()


    else:
        sleep(1)
        print(rdt.rdt_1_0_receive())
        rdt.rdt_1_0_send('MSG_FROM_SERVER')
    rdt.disconnect()
