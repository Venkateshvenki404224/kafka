from flask import Flask, request, jsonify
from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from pymongo import MongoClient
import threading
import json 
from src.Database import Database
from src import get_config
from flask_socketio import SocketIO, emit

application = app = Flask(__name__, static_folder='assets', static_url_path="/")
app.secret_key = get_config("secret_key")
socketio = SocketIO(app, cors_allowed_origins="*")
# Kafka setup
kafka_server = get_config("kafka_server")
producer = KafkaProducer(bootstrap_servers=[kafka_server],
                         value_serializer=lambda x: json.dumps(x).encode('utf-8'))

# MongoDB setup
db = Database.get_connection()
tickets_collection = db.tickets
messages_collection = db.messages

def create_topic(name):
    admin_client = KafkaAdminClient(bootstrap_servers=kafka_server)
    topic_list = [NewTopic(name=name, num_partitions=1, replication_factor=1)]
    admin_client.create_topics(new_topics=topic_list, validate_only=False)

def consume_messages():
    consumer = KafkaConsumer(bootstrap_servers=[kafka_server],
                             auto_offset_reset='earliest',
                             enable_auto_commit=True,
                             group_id='chat-consumer-group',
                             value_deserializer=lambda x: json.loads(x.decode('utf-8')))
    for message in consumer:
        message_data = message.value
        print(f"Storing message: {message_data}")
        socketio.emit('chat_message', message_data)
        
        # Ensure message_data is a dictionary before insertion
        if not isinstance(message_data, dict):
            print("Received message is not in dictionary format. Attempting to convert.")
            try:
                # Attempt to convert string message to dictionary if possible
                message_data = json.loads(message_data)
            except ValueError as e:
                print(f"Error converting message to dictionary: {e}")
                continue  # Skip this message if it can't be converted

        try:
            messages_collection.insert_one(message_data)
        except Exception as e:
            print(f"Failed to insert message into MongoDB: {e}")


# Start Kafka consumer thread
threading.Thread(target=consume_messages, daemon=True).start()

@app.route('/create_ticket', methods=['POST'])
def create_ticket():
    data = request.json
    ticket_id = tickets_collection.insert_one(data).inserted_id
    topic_name = f"ticket-{ticket_id}"
    create_topic(topic_name)
    return jsonify({"ticket_id": str(ticket_id), "topic": topic_name}), 200

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    topic = data['topic']
    message = data['message']
    producer.send(topic, message)
    producer.flush()
    return jsonify({"status": "Message sent to topic " + topic}), 200


socketio.start_background_task(consume_messages)


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
