import socket
import sys
import struct
import select
from time import sleep

class Network():
    # Message type constants
    MSG_AUTH = 0x00
    MSG_AUTH_RESPONSE = 0x01
    MSG_MAZE = 0x02
    MSG_PACMAN_ARRIVED = 0x10
    MSG_PACMAN_LEFT = 0x11
    MSG_PACMAN_DIED = 0x12
    MSG_PACMAN_HOME = 0x13
    MSG_PACMAN_UPDATE = 0x14
    MSG_GHOST_UPDATE = 0x15
    MSG_GHOST_EATEN = 0x16
    MSG_EAT = 0x17
    MSG_SCORE_UPDATE = 0x20
    MSG_LIVES_UPDATE = 0x21
    MSG_STATUS_UPDATE = 0x22
    
    # Auth response status codes
    AUTH_ACCEPTED = 0x01
    AUTH_REJECTED = 0x00
    
    def __init__(self, controller, password):
        self.__controller = controller
        self.__password = password
        self.__server = False
        self.__connected = False
        try:
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as err: 
            print("socket creation failed with error %s" %(err))
            sys.exit()
        self.__recv_buf = bytes()
        self.get_local_ip_addr()

    def server(self, port):
        self.__server = True
        while True:
            try:
                self.__sock.bind(('', port))
                break
            except OSError as err:
                print(err)
                print("waiting, will retry in 10 seconds")
                sleep(10)
  
        # put the socket into listening mode 
        self.__sock.listen(5)
        print("listening for incoming connection...")

        while True: 
            # Establish connection with client. 
            c_sock, addr = self.__sock.accept()
            
            # Receive AUTH message
            try:
                auth_msg = self._recv_message_blocking(c_sock)
                if auth_msg is None:
                    c_sock.close()
                    continue
                    
                msg_type, password = self._decode_auth(auth_msg)
                
                if password == self.__password:
                    # Send AUTH_RESPONSE with ACCEPTED
                    response = self._encode_auth_response(self.AUTH_ACCEPTED)
                    c_sock.send(response)
                    break
                else:
                    # Send AUTH_RESPONSE with REJECTED
                    response = self._encode_auth_response(self.AUTH_REJECTED)
                    c_sock.send(response)
                    c_sock.close()
            except Exception as e:
                print(f"Authentication error: {e}")
                c_sock.close()
                
        # swap the socket names so send/recv functions don't care if we're client or server
        self.__listen_sock = self.__sock
        self.__sock = c_sock
        self.__connected = True
            

    def client(self, ip, port):
        self.__sock.connect((ip, port))
        
        # Send AUTH message
        auth_msg = self._encode_auth(self.__password)
        self.__sock.send(auth_msg)
        
        # Receive AUTH_RESPONSE
        try:
            response = self._recv_message_blocking(self.__sock)
            if response is None:
                print("handshake failed: no response\n")
                return
                
            msg_type, status = self._decode_auth_response(response)
            
            if status == self.AUTH_ACCEPTED:
                self.__connected = True
            else:
                print("handshake failed: rejected\n")
        except Exception as e:
            print(f"handshake failed: {e}\n")

    def get_local_ip_addr(self):
        # ugly hacky way to find our IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # connect to nrg.cs.ucl.ac.uk
        s.connect(("128.16.66.166", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip

    @property
    def connected(self):
        return self.__connected

    # ========== ENCODING FUNCTIONS ==========
    
    def _encode_auth(self, password):
        """Encode AUTH message: [Length:2][Type:1][PassLen:1][Password:variable]"""
        password_bytes = password.encode('utf-8')
        pass_len = len(password_bytes)
        if pass_len > 255:
            raise ValueError("Password too long (max 255 bytes)")
        
        payload = struct.pack('>BB', self.MSG_AUTH, pass_len) + password_bytes
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_auth_response(self, status):
        """Encode AUTH_RESPONSE message: [Length:2][Type:1][Status:1]"""
        payload = struct.pack('>BB', self.MSG_AUTH_RESPONSE, status)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_maze(self, maze):
        """Encode MAZE message: [Length:2][Type:1][Width:2][Height:2][Data:variable]"""
        height = len(maze)
        width = len(maze[0]) if height > 0 else 0
        
        # Flatten 2D maze into bytes
        maze_data = bytes()
        for row in maze:
            for cell in row:
                maze_data += struct.pack('>B', cell)
        
        payload = struct.pack('>BHH', self.MSG_MAZE, width, height) + maze_data
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_empty_message(self, msg_type):
        """Encode message with no payload: [Length:2][Type:1]"""
        payload = struct.pack('>B', msg_type)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_pacman_update(self, pos, direction, speed):
        """Encode PACMAN_UPDATE: [Length:2][Type:1][X:8][Y:8][Dir:1][Speed:8]"""
        payload = struct.pack('>BdddBd', self.MSG_PACMAN_UPDATE, 
                            pos[0], pos[1], direction, speed)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_ghost_update(self, ghostnum, pos, dirn, speed, mode):
        """Encode GHOST_UPDATE: [Length:2][Type:1][GhostNum:1][X:8][Y:8][Dir:1][Speed:8][Mode:1]"""
        payload = struct.pack('>BBddBdB', self.MSG_GHOST_UPDATE,
                            ghostnum, pos[0], pos[1], dirn, speed, mode)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_ghost_eaten(self, ghostnum):
        """Encode GHOST_EATEN: [Length:2][Type:1][GhostNum:1]"""
        payload = struct.pack('>BB', self.MSG_GHOST_EATEN, ghostnum)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_eat(self, pos, is_foreign, is_powerpill):
        """Encode EAT: [Length:2][Type:1][X:1][Y:1][Flags:1]"""
        flags = 0
        if is_foreign:
            flags |= 0x01
        if is_powerpill:
            flags |= 0x02
        
        payload = struct.pack('>BBBB', self.MSG_EAT, pos[0], pos[1], flags)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_score_update(self, score):
        """Encode SCORE_UPDATE: [Length:2][Type:1][Score:4]"""
        payload = struct.pack('>BI', self.MSG_SCORE_UPDATE, score)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_lives_update(self, lives):
        """Encode LIVES_UPDATE: [Length:2][Type:1][Lives:1]"""
        payload = struct.pack('>BB', self.MSG_LIVES_UPDATE, lives)
        length = len(payload)
        return struct.pack('>H', length) + payload
    
    def _encode_status_update(self, status):
        """Encode STATUS_UPDATE: [Length:2][Type:1][Status:1]"""
        payload = struct.pack('>BB', self.MSG_STATUS_UPDATE, status)
        length = len(payload)
        return struct.pack('>H', length) + payload

    # ========== DECODING FUNCTIONS ==========
    
    def _decode_auth(self, data):
        """Decode AUTH message"""
        msg_type = struct.unpack('>B', data[0:1])[0]
        pass_len = struct.unpack('>B', data[1:2])[0]
        password = data[2:2+pass_len].decode('utf-8')
        return msg_type, password
    
    def _decode_auth_response(self, data):
        """Decode AUTH_RESPONSE message"""
        msg_type, status = struct.unpack('>BB', data[0:2])
        return msg_type, status
    
    def _decode_maze(self, data):
        """Decode MAZE message"""
        msg_type, width, height = struct.unpack('>BHH', data[0:5])
        
        # Reconstruct 2D maze
        maze = []
        offset = 5
        for y in range(height):
            row = []
            for x in range(width):
                cell = struct.unpack('>B', data[offset:offset+1])[0]
                row.append(cell)
                offset += 1
            maze.append(row)
        
        return maze
    
    def _decode_pacman_update(self, data):
        """Decode PACMAN_UPDATE message"""
        msg_type, x, y, direction, speed = struct.unpack('>BdddBd', data[0:26])
        pos = (x, y)
        return pos, direction, speed
    
    def _decode_ghost_update(self, data):
        """Decode GHOST_UPDATE message"""
        msg_type, ghostnum, x, y, dirn, speed, mode = struct.unpack('>BBddBdB', data[0:28])
        pos = (x, y)
        return ghostnum, pos, dirn, speed, mode
    
    def _decode_ghost_eaten(self, data):
        """Decode GHOST_EATEN message"""
        msg_type, ghostnum = struct.unpack('>BB', data[0:2])
        return ghostnum
    
    def _decode_eat(self, data):
        """Decode EAT message"""
        msg_type, x, y, flags = struct.unpack('>BBBB', data[0:4])
        pos = (x, y)
        is_foreign = bool(flags & 0x01)
        is_powerpill = bool(flags & 0x02)
        return pos, is_foreign, is_powerpill
    
    def _decode_score_update(self, data):
        """Decode SCORE_UPDATE message"""
        msg_type, score = struct.unpack('>BI', data[0:5])
        return score
    
    def _decode_lives_update(self, data):
        """Decode LIVES_UPDATE message"""
        msg_type, lives = struct.unpack('>BB', data[0:2])
        return lives
    
    def _decode_status_update(self, data):
        """Decode STATUS_UPDATE message"""
        msg_type, status = struct.unpack('>BB', data[0:2])
        return status

    # ========== SEND/RECEIVE FUNCTIONS ==========
    
    def _recv_message_blocking(self, sock):
        """Receive a complete message (blocking). Used during handshake."""
        # Receive length (2 bytes)
        length_bytes = b''
        while len(length_bytes) < 2:
            chunk = sock.recv(2 - len(length_bytes))
            if not chunk:
                return None
            length_bytes += chunk
        
        length = struct.unpack('>H', length_bytes)[0]
        
        # Receive payload
        payload = b''
        while len(payload) < length:
            chunk = sock.recv(length - len(payload))
            if not chunk:
                return None
            payload += chunk
        
        return payload

    def send_maze(self, maze):
        data = self._encode_maze(maze)
        self.__sock.send(data)

    def check_for_messages(self, now):
        rd, wd, ed = select.select([self.__sock],[],[],0)
        if not rd:
            pass
        else:
            try:
                recv_bytes = self.__sock.recv(10000)
            except ConnectionResetError as e:
                print("Remote game has quit: ", e)
                sys.exit()
            
            if not recv_bytes:
                print("Connection closed by remote")
                sys.exit()
                
            self.__recv_buf += recv_bytes  # concat onto whatever is left from prev receive
            
            # Process all complete messages in buffer
            while len(self.__recv_buf) >= 2:
                recv_len = struct.unpack('>H', self.__recv_buf[0:2])[0]
                
                # Check if we have the complete message
                if len(self.__recv_buf) - 2 >= recv_len:
                    self.parse_msg(self.__recv_buf[2:recv_len+2])
                    self.__recv_buf = self.__recv_buf[recv_len+2:]
                else:
                    break  # Wait for more data
                    
        
    def parse_msg(self, buf):
        if len(buf) == 0:
            return
            
        msg_type = struct.unpack('>B', buf[0:1])[0]
        
        if msg_type == self.MSG_MAZE:
            maze = self._decode_maze(buf)
            self.__controller.received_maze(maze)
            
        elif msg_type == self.MSG_PACMAN_ARRIVED:
            self.__controller.foreign_pacman_arrived()
            
        elif msg_type == self.MSG_PACMAN_LEFT:
            self.__controller.foreign_pacman_left()
            
        elif msg_type == self.MSG_PACMAN_DIED:
            self.__controller.foreign_pacman_died()
            
        elif msg_type == self.MSG_PACMAN_HOME:
            self.__controller.pacman_go_home()
            
        elif msg_type == self.MSG_PACMAN_UPDATE:
            pos, direction, speed = self._decode_pacman_update(buf)
            self.__controller.foreign_pacman_update(pos, direction, speed)
            
        elif msg_type == self.MSG_GHOST_UPDATE:
            ghostnum, pos, dirn, speed, mode = self._decode_ghost_update(buf)
            self.__controller.remote_ghost_update(ghostnum, pos, dirn, speed, mode)
            
        elif msg_type == self.MSG_GHOST_EATEN:
            ghostnum = self._decode_ghost_eaten(buf)
            self.__controller.foreign_pacman_ate_ghost(ghostnum)
            
        elif msg_type == self.MSG_EAT:
            pos, is_foreign, is_powerpill = self._decode_eat(buf)
            if is_foreign:
                self.__controller.foreign_eat(pos, is_powerpill)
            else:
                self.__controller.remote_eat(pos, is_powerpill)
                
        elif msg_type == self.MSG_SCORE_UPDATE:
            score = self._decode_score_update(buf)
            self.__controller.update_remote_score(score)
            
        elif msg_type == self.MSG_LIVES_UPDATE:
            lives = self._decode_lives_update(buf)
            self.__controller.update_remote_lives(lives)
            
        elif msg_type == self.MSG_STATUS_UPDATE:
            status = self._decode_status_update(buf)
            self.__controller.remote_status_update(status)
            
        else:
            print(f"Unknown message type: 0x{msg_type:02X}")

    # ========== PUBLIC SEND FUNCTIONS ==========

    def send_foreign_pacman_arrived(self):
        data = self._encode_empty_message(self.MSG_PACMAN_ARRIVED)
        self.__sock.send(data)

    def send_foreign_pacman_left(self):
        data = self._encode_empty_message(self.MSG_PACMAN_LEFT)
        self.__sock.send(data)

    def send_foreign_pacman_died(self):
        data = self._encode_empty_message(self.MSG_PACMAN_DIED)
        self.__sock.send(data)

    def send_pacman_go_home(self):
        data = self._encode_empty_message(self.MSG_PACMAN_HOME)
        self.__sock.send(data)

    def send_pacman_update(self, pos, dir, speed):
        data = self._encode_pacman_update(pos, dir, speed)
        self.__sock.send(data)
        
    def send_ghost_update(self, ghostnum, pos, dirn, speed, mode):
        data = self._encode_ghost_update(ghostnum, pos, dirn, speed, mode)
        self.__sock.send(data)

    def send_foreign_pacman_ate_ghost(self, ghostnum):
        data = self._encode_ghost_eaten(ghostnum)
        self.__sock.send(data)

    def send_eat(self, pos, is_foreign, is_powerpill):
        data = self._encode_eat(pos, is_foreign, is_powerpill)
        self.__sock.send(data)

    def send_score_update(self, score):
        data = self._encode_score_update(score)
        self.__sock.send(data)
        
    def send_lives_update(self, lives):
        data = self._encode_lives_update(lives)
        self.__sock.send(data)
        
    def send_status_update(self, status):
        data = self._encode_status_update(status)
        self.__sock.send(data)
