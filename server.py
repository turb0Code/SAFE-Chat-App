import threading
import socket
import time
from tinyec import registry
import secrets
from tinyec import ec
import sys
import pymongo
import signal

##############################

class Encryption:

    curve = registry.get_curve('brainpoolP256r1')
    modulo = sys.maxunicode

    @staticmethod
    def create_pv_key():
        return secrets.randbelow(Encryption.curve.field.n)

    @staticmethod
    def create_pub_key(pv_key):
        return pv_key * Encryption.curve.g

    @staticmethod
    def force_create_point(x, y):
        return ec.Point(Encryption.curve, x, y)

    @staticmethod
    def encrypt(message, key):
        return ''.join(chr((ord(c) + key.x) % Encryption.modulo) for c in message)

    @staticmethod
    def decrypt(message, key):
        return ''.join(chr((ord(c) - key.x) % Encryption.modulo) for c in message)

##############################

class Database:

    @staticmethod
    def connect():
        DB_CLIENT = pymongo.MongoClient("mongodb://localhost:27017/")

        DB = DB_CLIENT["database"]

        COLLECTION = DB["users"]

        print(DB_CLIENT.list_database_names())

        return COLLECTION

    @staticmethod
    def start():
        Database.COLLECTION = Database.connect()

    @staticmethod
    def register(login, password, confirmation, user_id, token):
        if password != confirmation:
            return

        data = {"user_id" : user_id, "username" : login, "password" : password, "token" : token, "friends" : []}
        Database.COLLECTION.insert_one(data)

    @staticmethod
    def login(login, password):
        result = Database.COLLECTION.find({"username" : login, "password" : password})
        try:
            if result[0]["username"] == login:
                return True
            else:
                return False
        except:
            return False

    @staticmethod
    def password_recovery(token, password):
        Database.COLLECTION.update_one({"token" : token}, { "$set" : {"password" : password}})
        print(Database.COLLECTION.find({"token" : token})[0])

    @staticmethod
    def get_friends(username):
        result = Database.COLLECTION.find_one({"username" : username})
        friends = []
        for i in range(len(result["friends"])):
            friends.append(f"{result['friends'][i][1]} | {result['friends'][i][0]}")
        return friends

    @staticmethod
    def add_friend(username, friend_id, friend_name):
        result = Database.COLLECTION.find_one({"username" : friend_name, "user_id" : friend_id})
        try:
            if result["user_id"] == friend_id:
                Database.COLLECTION.update_one({"username" : username}, { "$push" : {"friends" : [friend_id, friend_name]}})
                print(f"Successfully added new friend {friend_name}")
                # TODO: SEND TO USER FRIEND LIST AND SEND SUCCESS
            else:
                print("USER NOT FOUND!")
                # TODO: SEND ERROR
        except:
            print("USER NOT FOUND!")
            # TODO: SEND ERROR

##############################

class Background:

    @staticmethod
    def ctrl_c_handler(sig, frame):
        print("\n" + "-"*20 + "\nThank's for using SAFE CHAT APP SERVER!")
        print("SERVER STOPPED...")
        print("EXITING...")
        exit(0)


##############################

class Client():
    client = ''
    ip = ''
    username = ''
    chat_id = ''

    def __init__(self, client, ip, username, chat_room):
        self.client = client
        self.ip = ip
        self.username = username
        self.chat_id = chat_room

    @staticmethod
    def auth_user(client, addr):
        while True:

            recieved = client.recv(1023).decode('utf-8')

            if recieved == "//EXIT":
                print(f"Client {str(addr)} disconnected at the beginning.")
                client.close()
                return False
            else:
                if recieved == "//LOGIN":
                    recieved = client.recv(1024).decode('utf-8').split("^^")
                    login = recieved[0]
                    password = recieved[1]
                    if Database.login(login, password):
                        client.send("//OK".encode('utf-8'))
                        return True
                    else:
                        client.send("//ERROR[LOGIN]".encode('utf-8'))
                        continue
                elif recieved == "//REGISTER":
                    recieved = client.recv(1024).decode('utf-8')
                    if recieved != "//ERROR":
                        recieved = recieved.split("^^")
                        login = recieved[0]
                        password = recieved[1]
                        password_confirm = recieved[2]
                        user_id = recieved[3]
                        token = recieved[4]
                        Database.register(login, password, password_confirm, user_id, token)
                        return True
                    continue
                elif recieved == "//FORGOT":
                    token = client.recv(1024).decode('utf-8')
                    result = Database.COLLECTION.find_one({"token" : token})
                    try:
                        result["token"]
                        client.send("//OK".encode('utf-8'))
                        password = client.recv(1024).decode('utf-8')
                        Database.password_recovery(token, password)
                    except:
                        client.send("//INVALID".encode('utf-8'))
                    continue

    @staticmethod
    def generate_chat_id(first_user, second_user):
        first_output = 0
        second_output = 0

        if len(first_user) > len(second_user):
            lenght = len(second_user)
        else:
            lenght = len(first_user)

        for i in range(lenght):
            tmp = i * ord(first_user[i])
            first_output += tmp

        for i in range(lenght):
            tmp = i * ord(second_user[i])
            second_output += tmp

        return first_output * second_output

    @staticmethod
    def get_chat_id(client, nickname, ecc_shared):

        client.send(f"{Database.get_friends(nickname)}".encode('utf-8'))

        print(Database.get_friends(nickname))

        while True:

            recieved = client.recv(1024).decode('utf-8')

            if recieved == "//EXIT":
                print(f"User {nickname} disconnected!")
                client.close()
                return ""
            elif recieved == "//NEW[USER]":
                recieved = client.recv(1024).decode('utf-8').split("^^")
                Database.add_friend(nickname, recieved[0], recieved[1])
                client.send(f"{Database.get_friends(nickname)}".encode('utf-8'))
            elif recieved == "//PICK":
                recieved = Encryption.decrypt(client.recv(1024).decode('utf-8'), ecc_shared).split(" | ")[0]
                chat_id = Client.generate_chat_id(nickname, recieved)
                return chat_id
            else:
                client.close() # TODO: kick out client
                return ""

    @staticmethod
    def connect():
        Database.start()

        while True:

            client, addr = server.accept()

            ecc_pv = Encryption.create_pv_key()
            ecc_pb = Encryption.create_pub_key(ecc_pv)

            client.send(f"//KEY->{ecc_pb.x},{ecc_pb.y}".encode('utf-8'))
            ecc_user_pb = client.recv(1024).decode('utf-8').split(",")
            ecc_user_pb = Encryption.force_create_point(int(ecc_user_pb[0]), int(ecc_user_pb[1]))

            ecc_shared =  ecc_user_pb * ecc_pv
            print(f"X: {ecc_shared.x} \nY: {ecc_shared.y}")

            if not Client.auth_user(client, addr):
                continue

            client.send(Encryption.encrypt("//NICKNAME", ecc_shared).encode('utf-8'))
            nickname = Encryption.decrypt(client.recv(1024).decode('utf-8'), ecc_shared)
            nicknames.append(nickname)

            thread = threading.Thread(target=Chat.handle, args=(client, nickname, addr, ecc_shared, ))
            thread_pool.append(thread)
            thread.start()

            del nickname, client, addr,
            time.sleep(0.5)

##############################

class Room:
    clients = []
    id = ""

    def __init__(self, id):
        self.id = id

    def add_user(self, client):
        self.clients.append(client)

    def del_client(self, client):
        self.clients.remove(client)

##############################

class Chat:
    users = []
    name = ""
    id = ""

    def __init__(self, name):
        self.name = name
        self.id = 1

    @staticmethod
    def broadcast(message, chat_id_index):
        print(f'MSG: {message}')
        for client in rooms[chat_id_index].clients:
            client.client.send(message)

    @staticmethod
    def chatting(client, nickname):
        while True:

            #chat_id_index = [room.id for room in rooms].index(client.chat_id) ---COMMENTED---
            chat_id_index = 0

            try:
                recieved = client.client.recv(1024)
                if "//EXIT".encode('utf-8') in recieved:
                    client.client.send("//EXIT".encode('utf-8'))
                    rooms[chat_id_index].del_client(client)
                    print(f"User {nickname} left chat.")
                    return True
                else:
                    Chat.broadcast(recieved, chat_id_index)
            except:
                print("DELETING USER")
                Chat.users.remove(client)
                client.client.close()
                nicknames.remove(nickname)
                Chat.broadcast(f"{nickname} LEFT CHAT".encode('utf-8'), chat_id_index)
                return False

    @staticmethod
    def handle(client, nickname, addr, ecc_shared):

        ecc_shared_user = ecc_shared

        while True:

            client.send(Encryption.encrypt("//CHATROOM", ecc_shared_user).encode('utf-8'))
            chat_id = Client.get_chat_id(client, nickname, ecc_shared_user) #TODO: CHANGE IT!
            if chat_id == "":
                break
            new_client = Client(client, addr, nickname, chat_id)

            Chat.users.append(new_client)

            indexx = Chat.users.index(new_client)

            rooms_ids = [room.id for room in rooms]

            if new_client.chat_id in rooms_ids:
                room = rooms[rooms_ids.index(new_client.chat_id)]
                room.add_user(new_client)
                #room_id_index = rooms_ids.index(new_client.chat_id) ---COMMENTED---
                room_id_index = 0
            else:
                rooms.append(Room(new_client.chat_id))
                room_id_index = -1
                rooms[room_id_index].add_user(new_client)


            print(f"Connected with {str(addr)} as {nickname} to chat {new_client.chat_id}.")

            chat_id_index = 0

            Chat.broadcast(f"{nickname} JOINED CHAT.".encode('utf-8'), chat_id_index)

            if not Chat.chatting(new_client, nickname):
                break
        return

##############################


signal.signal(signal.SIGINT, Background.ctrl_c_handler)

ADDRESS = "127.0.0.1"
PORT = 9999

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((ADDRESS, PORT))

clients = []
rooms = []

server.listen()

nicknames = []
thread_pool = []

print(r"""
__  _   ___  ___    __  _ _   _  ___    _   ___ ___
/ _|/ \ | __|| __|  / _|| U | / \|_ _|  / \ | o \ o \
\_ \ o || _| | _|  ( (_ |   || o || |  | o ||  _/  _/
|__/_n_||_|  |___|  \__||_n_||_n_||_|  |_n_||_| |_|
__  ___  ___ _ _  ___  ___
/ _|| __|| o \ | || __|| o \
\_ \| _| |   / V || _| |   /
|__/|___||_|\\\_/ |___||_|\\
""")

print("-"*20)
print("Running server...")

Client.connect()
