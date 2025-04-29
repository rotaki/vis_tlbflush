import socket, time
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(("127.0.0.1", 8089))

lp = f"dummy,batch=test value=123i {time.time_ns()}\n"
sock.send(lp.encode())
print("sent:", lp.strip())