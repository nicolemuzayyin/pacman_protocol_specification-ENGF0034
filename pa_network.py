import socket
import sys
import struct
import select
from time import sleep, time

class Network():
    def __init__(self, controller, password):
        self.__controller = controller
        self.__password = password
        self.__server = False
        self.__connected = False
        
        # TCP socket
        try:
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as err: 
            print("TCP socket creation failed with error %s" %(err))
            sys.exit()
        
        # UDP socket (initialized after SYNC_START)
        self.__udp_sock = None
        self.__udp_port = 5433
        self.__remote_addr = None
        
        # Sequence numbers for UDP
        self.__udp_seq = 0
        self.__last_recv_seq = {}  # Per message type
        
        # TCP receive buffer
        self.__recv_buf = bytes()
        
        self.get_local_ip_addr()

    def server(self, port=5432):
        """Server mode - listen and accept connection"""
        self.__server = True
        
        # Bind with retry logic
        while True:
            try:
                self.__sock.bind(('', port))
                break
            except OSError as err:
                print(err)
                print("waiting, will retry in 10 seconds")
                sleep(10)
        
        # Listen for connections
        self.__sock.listen(5)
        print(f"Server listening on port {port}...")
        
        # Accept connection and validate password
        while True:
            c_sock, addr = self.__sock.accept()
            print(f'Connection attempt from {addr}')
            
            # Receive PASSWORD_EXCHANGE message
            try:
                msg = c_sock.recv(18)  # 2 length + 16 password
                if len(msg) < 18:
                    c_sock.close()
                    continue
                
                length = struct.unpack('!H', msg[0:2])[0]
                msg_type = (msg[2] >> 4) & 0x0F
                
                if msg_type != 0x1:  # Not PASSWORD_EXCHANGE
                    c_sock.close()
                    continue
                
                # Extract password (null-terminated)
                password_bytes = msg[2:18]
                try:
                    password = password_bytes.split(b'\x00')[0].decode('ascii')
                except:
                    c_sock.close()
                    continue
                
                if password == self.__password:
                    print("Password validated")
                    break
                else:
                    print("Invalid password")
                    c_sock.close()
            except Exception as e:
                print(f"Error during handshake: {e}")
                c_sock.close()
        
        # Swap sockets
        self.__listen_sock = self.__sock
        self.__sock = c_sock
        self.__remote_addr = (addr[0], self.__udp_port)
        
        # Exchange mazes
        self.send_maze(self.__controller.get_maze())
        remote_maze = self.receive_maze()
        if remote_maze:
            self.__controller.received_maze(remote_maze)
        
        # Send SYNC_START
        start_time = int(time()) + 2  # Start in 2 seconds
        self.send_sync_start(start_time)
        
        # Wait until start time
        while time() < start_time:
            sleep(0.01)
        
        # Initialize UDP
        self.init_udp()
        self.__connected = True
        print("Game synchronized and starting!")

    def client(self, ip, port=5432):
        """Client mode - connect to server"""
        try:
            self.__sock.connect((ip, port))
            self.__remote_addr = (ip, self.__udp_port)
        except Exception as e:
            print(f"Connection failed: {e}")
            sys.exit()
        
        # Send PASSWORD_EXCHANGE
        self.send_password_exchange()
        
        # Exchange mazes
        remote_maze = self.receive_maze()
        if remote_maze:
            self.__controller.received_maze(remote_maze)
        self.send_maze(self.__controller.get_maze())
        
        # Receive SYNC_START
        start_time = self.receive_sync_start()
        if start_time:
            print(f"Synchronized, starting at {start_time}")
            
            # Wait until start time
            while time() < start_time:
                sleep(0.01)
        
        # Initialize UDP
        self.init_udp()
        self.__connected = True
        print("Game synchronized and starting!")

    def init_udp(self):
        """Initialize UDP socket after synchronization"""
        try:
            self.__udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.__udp_sock.bind(('', self.__udp_port))
            self.__udp_sock.setblocking(False)
            self.__udp_seq = 0
            print(f"UDP socket initialized on port {self.__udp_port}")
        except Exception as e:
            print(f"UDP socket creation failed: {e}")

    def get_local_ip_addr(self):
        """Get local IP address"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    @property
    def connected(self):
        return self.__connected

    # ==================== PASSWORD EXCHANGE ====================
    
    def send_password_exchange(self):
        """Send PASSWORD_EXCHANGE message (Type 0x1)"""
        length = 16
        msg = struct.pack('!H', length)
        
        # Encode password in first byte's lower nibble + 15 bytes
        password_bytes = self.__password.encode('ascii')[:15]
        password_bytes += b'\x00' * (15 - len(password_bytes))  # Pad with nulls
        
        # First byte: type (0x1) in upper nibble
        msg += bytes([0x10]) + password_bytes
        
        self.__sock.send(msg)

    # ==================== SYNC_START ====================
    
    def send_sync_start(self, start_time):
        """Send SYNC_START message (Type 0x2)"""
        length = 5
        msg = struct.pack('!H', length)
        msg += bytes([0x20])  # Type 0x2
        msg += struct.pack('!I', start_time)
        self.__sock.send(msg)
    
    def receive_sync_start(self):
        """Receive SYNC_START message"""
        try:
            msg = self.__sock.recv(7)  # 2 length + 5 message
            if len(msg) < 7:
                return None
            
            length = struct.unpack('!H', msg[0:2])[0]
            msg_type = (msg[2] >> 4) & 0x0F
            
            if msg_type == 0x2:
                start_time = struct.unpack('!I', msg[3:7])[0]
                return start_time
        except Exception as e:
            print(f"Error receiving SYNC_START: {e}")
        return None

    # ==================== MAZE_UPDATE ====================
    
    def send_maze(self, maze):
        """Send MAZE_UPDATE message (Type 0x3)"""
        length = 435  # 1 type + 434 maze bytes
        msg = struct.pack('!H', length)
        msg += bytes([0x30])  # Type 0x3
        
        # Encode 868 squares as 4-bit values (2 per byte)
        maze_bytes = bytearray()
        for i in range(0, 868, 2):
            square1 = self.get_square_type(maze, i)
            square2 = self.get_square_type(maze, i + 1) if i + 1 < 868 else 0
            maze_bytes.append((square1 << 4) | square2)
        
        msg += bytes(maze_bytes)
        self.__sock.send(msg)
    
    def receive_maze(self):
        """Receive MAZE_UPDATE message"""
        try:
            # Receive length
            length_bytes = self.__sock.recv(2)
            if len(length_bytes) < 2:
                return None
            
            length = struct.unpack('!H', length_bytes)[0]
            
            # Receive message body
            msg = b''
            while len(msg) < length:
                chunk = self.__sock.recv(length - len(msg))
                if not chunk:
                    return None
                msg += chunk
            
            msg_type = (msg[0] >> 4) & 0x0F
            
            if msg_type == 0x3:
                # Decode maze
                maze_data = []
                for i in range(1, len(msg)):
                    square1 = (msg[i] >> 4) & 0x0F
                    square2 = msg[i] & 0x0F
                    maze_data.append(square1)
                    if len(maze_data) < 868:
                        maze_data.append(square2)
                
                return maze_data[:868]
        except Exception as e:
            print(f"Error receiving maze: {e}")
        return None
    
    def get_square_type(self, maze, index):
        """Convert maze square to 4-bit type code"""
        # This depends on your maze representation
        # Assuming maze has a method to get square type
        try:
            square = maze.get_square(index)
            if hasattr(square, 'type'):
                return square.type & 0x0F
            return 0
        except:
            return 0

    # ==================== GAME_MODE_UPDATE ====================
    
    def send_game_mode_update(self, mode, duration):
        """Send GAME_MODE_UPDATE message (Type 0x4)"""
        length = 3
        msg = struct.pack('!H', length)
        msg += bytes([0x40 | (mode & 0x03)])  # Type + mode
        msg += struct.pack('!H', duration)
        self.__sock.send(msg)

    # ==================== PACMAN_UPDATE (UDP) ====================
    
    def send_pacman_update(self, pos, direction, speed):
        """Send PACMAN_UPDATE message via UDP (Type 0x5)"""
        if not self.__udp_sock or not self.__remote_addr:
            return
        
        length = 6
        seq = self.__udp_seq
        
        x, y = pos
        # Clamp to 10 bits
        x = int(x) & 0x3FF
        y = int(y) & 0x3FF
        
        # Build message
        msg = struct.pack('!HH', length, seq)
        msg += bytes([0x50])  # Type 0x5
        
        # Pack position (10 bits X, 10 bits Y)
        pos_x_high = (x >> 2) & 0xFF
        pos_x_low_y_high = ((x & 0x03) << 6) | ((y >> 4) & 0x3F)
        pos_y_low_dir = ((y & 0x0F) << 4) | ((direction & 0x07) << 1)
        
        # Add speed bit
        if speed > 0:
            pos_y_low_dir |= 0x01
        
        msg += bytes([pos_x_high, pos_x_low_y_high, pos_y_low_dir])
        
        try:
            self.__udp_sock.sendto(msg, self.__remote_addr)
            self.__udp_seq = (self.__udp_seq + 1) % 65536
        except Exception as e:
            print(f"UDP send error: {e}")

    # ==================== GHOST_UPDATE (UDP) ====================
    
    def send_ghost_update(self, ghostnum, pos, direction, speed, mode):
        """Send GHOST_UPDATE message via UDP (Type 0x6)"""
        if not self.__udp_sock or not self.__remote_addr:
            return
        
        length = 7
        seq = self.__udp_seq
        
        x, y = pos
        x = int(x) & 0x3FF
        y = int(y) & 0x3FF
        
        # Build message
        msg = struct.pack('!HH', length, seq)
        msg += bytes([0x60 | (ghostnum & 0x03)])  # Type + ghost number
        
        # Pack position
        pos_x_high = (x >> 2) & 0xFF
        pos_x_low_y_high = ((x & 0x03) << 6) | ((y >> 4) & 0x3F)
        pos_y_low_dir = ((y & 0x0F) << 4) | ((direction & 0x07) << 1)
        
        # Add speed bit
        if speed > 0:
            pos_y_low_dir |= 0x01
        
        msg += bytes([pos_x_high, pos_x_low_y_high, pos_y_low_dir])
        msg += bytes([mode & 0x03])
        
        try:
            self.__udp_sock.sendto(msg, self.__remote_addr)
            self.__udp_seq = (self.__udp_seq + 1) % 65536
        except Exception as e:
            print(f"UDP send error: {e}")

    # ==================== PACMAN_UPDATE_2 ====================
    
    def send_foreign_pacman_arrived(self):
        """Foreign Pacman arrived on local screen"""
        self.send_pacman_update_2(foreign_status=1, dead=0, go_home=0)
    
    def send_foreign_pacman_left(self):
        """Foreign Pacman left local screen"""
        self.send_pacman_update_2(foreign_status=2, dead=0, go_home=0)
    
    def send_foreign_pacman_died(self):
        """Foreign Pacman died"""
        self.send_pacman_update_2(foreign_status=0, dead=1, go_home=0)
    
    def send_pacman_go_home(self):
        """Pacman must go home"""
        self.send_pacman_update_2(foreign_status=0, dead=0, go_home=1)
    
    def send_pacman_update_2(self, foreign_status, dead, go_home):
        """Send PACMAN_UPDATE_2 message (Type 0x7)"""
        length = 2
        msg = struct.pack('!H', length)
        msg += bytes([0x70])  # Type 0x7
        
        # Pack status bits
        status_byte = ((foreign_status & 0x03) << 3) | ((dead & 0x01) << 1) | (go_home & 0x01)
        msg += bytes([status_byte])
        
        self.__sock.send(msg)

    # ==================== EAT ====================
    
    def send_eat(self, pos, is_foreign, is_powerpill):
        """Send EAT message (Type 0x8)"""
        # Convert old parameters to new format
        if is_powerpill:
            food_type = 2  # Power pill
        elif is_foreign:
            food_type = 1  # Foreign ate
        else:
            food_type = 0  # Normal food
        
        self.send_eat_new(pos, food_type, 0, 0)
    
    def send_foreign_pacman_ate_ghost(self, ghostnum):
        """Foreign Pacman ate a ghost"""
        # Send with ghost_eaten field
        self.send_eat_new((0, 0), 0, 0, ghostnum)
    
    def send_eat_new(self, pos, food_type, ghost_eaten, foreign_ate_ghost):
        """Send EAT message (Type 0x8)"""
        length = 5
        msg = struct.pack('!H', length)
        
        x, y = pos
        x = int(x) & 0x3FF
        y = int(y) & 0x3FF
        
        # Type byte with food type
        msg += bytes([0x80 | (food_type & 0x03)])
        
        # Pack position
        pos_x_high = (x >> 2) & 0xFF
        pos_x_low_y_high = ((x & 0x03) << 6) | ((y >> 4) & 0x3F)
        pos_y_low_ghost = ((y & 0x0F) << 4) | (ghost_eaten & 0x0F)
        
        msg += bytes([pos_x_high, pos_x_low_y_high, pos_y_low_ghost])
        msg += bytes([foreign_ate_ghost & 0x0F])
        
        self.__sock.send(msg)

    # ==================== LIVES_SCORE_UPDATE ====================
    
    def send_score_update(self, score):
        """Send score update (combined with lives)"""
        lives = self.__controller.get_lives() if hasattr(self.__controller, 'get_lives') else 3
        self.send_lives_score_update(lives, score)
    
    def send_lives_update(self, lives):
        """Send lives update (combined with score)"""
        score = self.__controller.get_score() if hasattr(self.__controller, 'get_score') else 0
        self.send_lives_score_update(lives, score)
    
    def send_lives_score_update(self, lives, score):
        """Send LIVES_SCORE_UPDATE message (Type 0x9)"""
        length = 4
        msg = struct.pack('!H', length)
        
        # Type byte with lives
        msg += bytes([0x90 | (lives & 0x07)])
        
        # Pack 22-bit score
        score = score & 0x3FFFFF  # Clamp to 22 bits
        score_high = (score >> 14) & 0xFF
        score_mid = (score >> 6) & 0xFF
        score_low = (score << 2) & 0xFC
        
        msg += bytes([score_high, score_mid, score_low])
        
        self.__sock.send(msg)

    # ==================== STATUS_UPDATE ====================
    
    def send_status_update(self, status):
        """Send STATUS_UPDATE message (Type 0xA)"""
        length = 2
        msg = struct.pack('!H', length)
        msg += bytes([0xA0])  # Type 0xA
        msg += bytes([status & 0x03])
        self.__sock.send(msg)

    # ==================== MESSAGE RECEIVING ====================
    
    def check_for_messages(self, now):
        """Check for incoming TCP and UDP messages"""
        # Check TCP
        rd, wd, ed = select.select([self.__sock], [], [], 0)
        if rd:
            try:
                recv_bytes = self.__sock.recv(10000)
                if not recv_bytes:
                    print("Connection closed")
                    sys.exit()
                self.__recv_buf += recv_bytes
                self.process_tcp_buffer()
            except ConnectionResetError as e:
                print("Remote game has quit:", e)
                sys.exit()
            except Exception as e:
                print(f"TCP receive error: {e}")
        
        # Check UDP
        if self.__udp_sock:
            try:
                while True:
                    data, addr = self.__udp_sock.recvfrom(1024)
                    self.parse_udp_msg(data)
            except BlockingIOError:
                pass  # No more UDP messages
            except Exception as e:
                print(f"UDP receive error: {e}")
    
    def process_tcp_buffer(self):
        """Process TCP receive buffer"""
        while len(self.__recv_buf) >= 2:
            # Get message length
            length = struct.unpack('!H', self.__recv_buf[0:2])[0]
            
            # Check if we have the full message
            if len(self.__recv_buf) < 2 + length:
                break
            
            # Extract and parse message
            msg = self.__recv_buf[2:2+length]
            self.parse_tcp_msg(msg)
            
            # Remove from buffer
            self.__recv_buf = self.__recv_buf[2+length:]
    
    def parse_tcp_msg(self, msg):
        """Parse TCP message"""
        if len(msg) < 1:
            return
        
        msg_type = (msg[0] >> 4) & 0x0F
        
        if msg_type == 0x3:  # MAZE_UPDATE
            self.handle_maze_update(msg)
        elif msg_type == 0x4:  # GAME_MODE_UPDATE
            self.handle_game_mode_update(msg)
        elif msg_type == 0x7:  # PACMAN_UPDATE_2
            self.handle_pacman_update_2(msg)
        elif msg_type == 0x8:  # EAT
            self.handle_eat(msg)
        elif msg_type == 0x9:  # LIVES_SCORE_UPDATE
            self.handle_lives_score_update(msg)
        elif msg_type == 0xA:  # STATUS_UPDATE
            self.handle_status_update(msg)
        else:
            print(f"Unknown TCP message type: 0x{msg_type:X}")
    
    def parse_udp_msg(self, data):
        """Parse UDP message"""
        if len(data) < 5:
            return
        
        length = struct.unpack('!H', data[0:2])[0]
        seq = struct.unpack('!H', data[2:4])[0]
        msg_type = (data[4] >> 4) & 0x0F
        
        # Check sequence number (simple duplicate detection)
        if msg_type not in self.__last_recv_seq:
            self.__last_recv_seq[msg_type] = -1
        
        # Allow wrap-around
        seq_diff = (seq - self.__last_recv_seq[msg_type]) & 0xFFFF
        if seq_diff == 0:
            return  # Duplicate
        
        self.__last_recv_seq[msg_type] = seq
        
        if msg_type == 0x5:  # PACMAN_UPDATE
            self.handle_pacman_update(data[4:])
        elif msg_type == 0x6:  # GHOST_UPDATE
            self.handle_ghost_update(data[4:])
        else:
            print(f"Unknown UDP message type: 0x{msg_type:X}")

    # ==================== MESSAGE HANDLERS ====================
    
    def handle_maze_update(self, msg):
        """Handle MAZE_UPDATE message"""
        # Already handled in receive_maze()
        pass
    
    def handle_game_mode_update(self, msg):
        """Handle GAME_MODE_UPDATE message"""
        if len(msg) < 3:
            return
        
        mode = msg[0] & 0x03
        duration = struct.unpack('!H', msg[1:3])[0]
        
        # Notify controller
        if hasattr(self.__controller, 'game_mode_update'):
            self.__controller.game_mode_update(mode, duration)
    
    def handle_pacman_update(self, msg):
        """Handle PACMAN_UPDATE message (UDP)"""
        if len(msg) < 4:
            return
        
        # Unpack position
        pos_x_high = msg[1]
        pos_x_low_y_high = msg[2]
        pos_y_low_dir = msg[3]
        
        x = (pos_x_high << 2) | ((pos_x_low_y_high >> 6) & 0x03)
        y = ((pos_x_low_y_high & 0x3F) << 4) | ((pos_y_low_dir >> 4) & 0x0F)
        direction = (pos_y_low_dir >> 1) & 0x07
        speed = 1 if (pos_y_low_dir & 0x01) else 0
        
        pos = (x, y)
        self.__controller.foreign_pacman_update(pos, direction, speed)
    
    def handle_ghost_update(self, msg):
        """Handle GHOST_UPDATE message (UDP)"""
        if len(msg) < 5:
            return
        
        ghostnum = msg[0] & 0x03
        
        # Unpack position
        pos_x_high = msg[1]
        pos_x_low_y_high = msg[2]
        pos_y_low_dir = msg[3]
        mode = msg[4] & 0x03
        
        x = (pos_x_high << 2) | ((pos_x_low_y_high >> 6) & 0x03)
        y = ((pos_x_low_y_high & 0x3F) << 4) | ((pos_y_low_dir >> 4) & 0x0F)
        direction = (pos_y_low_dir >> 1) & 0x07
        speed = 1 if (pos_y_low_dir & 0x01) else 0
        
        pos = (x, y)
        self.__controller.remote_ghost_update(ghostnum, pos, direction, speed, mode)
    
    def handle_pacman_update_2(self, msg):
        """Handle PACMAN_UPDATE_2 message"""
        if len(msg) < 2:
            return
        
        status_byte = msg[1]
        foreign_status = (status_byte >> 3) & 0x03
        dead = (status_byte >> 1) & 0x01
        go_home = status_byte & 0x01
        
        if foreign_status == 1:
            self.__controller.foreign_pacman_arrived()
        elif foreign_status == 2:
            self.__controller.foreign_pacman_left()
        
        if dead:
            self.__controller.foreign_pacman_died()
        
        if go_home:
            self.__controller.pacman_go_home()
    
    def handle_eat(self, msg):
        """Handle EAT message"""
        if len(msg) < 5:
            return
        
        food_type = msg[0] & 0x03
        
        # Unpack position
        pos_x_high = msg[1]
        pos_x_low_y_high = msg[2]
        pos_y_low_ghost = msg[3]
        foreign_ate_ghost = msg[4] & 0x0F
        
        x = (pos_x_high << 2) | ((pos_x_low_y_high >> 6) & 0x03)
        y = ((pos_x_low_y_high & 0x3F) << 4) | ((pos_y_low_ghost >> 4) & 0x0F)
        ghost_eaten = pos_y_low_ghost & 0x0F
        
        pos = (x, y)
        
        # Handle different cases
        if foreign_ate_ghost > 0:
            # Foreign pacman ate our ghost
            self.__controller.foreign_pacman_ate_ghost(foreign_ate_ghost)
        elif food_type == 2:
            # Power pill eaten
            is_foreign = True  # Assume foreign for now
            self.__controller.foreign_eat(pos, True)
        elif food_type == 1:
            # Foreign ate normal food
            self.__controller.foreign_eat(pos, False)
        else:
            # Remote ate food
            self.__controller.remote_eat(pos, False)
    
    def handle_lives_score_update(self, msg):
        """Handle LIVES_SCORE_UPDATE message"""
        if len(msg) < 4:
            return
        
        lives = msg[0] & 0x07
        
        # Unpack 22-bit score
        score_high = msg[1]
        score_mid = msg[2]
        score_low = msg[3]
        
        score = (score_high << 14) | (score_mid << 6) | (score_low >> 2)
        
        self.__controller.update_remote_lives(lives)
        self.__controller.update_remote_score(score)
    
    def handle_status_update(self, msg):
        """Handle STATUS_UPDATE message"""
        if len(msg) < 2:
            return
        
        status = msg[1] & 0x03
        self.__controller.remote_status_update(status)
