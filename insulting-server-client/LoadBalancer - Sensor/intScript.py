import getopt
import pickle
import random
import signal
import sys
import threading
import time
import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from concurrent import futures

import redis
import multiprocessing
import grpc_sensor
import grpc_server
import sensorLoadBalancer_pb2
import grpc_LoadBalancerServer
import sensorLoadBalancer_pb2_grpc
import grpc_proxy
import grpc_terminal

import loadBalancerServer_pb2_grpc
import loadBalancerServer_pb2


def main():
    pollutionSensors = 1
    qualitySensors = 1
    servers_num = 2
    terminals = 2

    argv = sys.argv[1:]

    opts, args = getopt.getopt(argv, "p:q:s:t:",
                               ["pollution_sensor=",
                                "quality_sensor=",
                                "servers=",
                                "terminals="])

    for opt, arg in opts:
        if opt in ['-p', '--pollution_sensor']:
            pollutionSensors = arg
        elif opt in ['-q', '--quality_sensor']:
            qualitySensors = arg
        elif opt in ['-s', '--servers']:
            servers_num = arg
        elif opt in ['-t', '--terminals']:
            terminals = arg

    r = redis.Redis(host='localhost', port=6379)
    pollution = dict()
    wellness = dict()

    pollution_bytes = pickle.dumps(pollution)
    wellness_bytes = pickle.dumps(wellness)

    r.set('pollution', pollution_bytes)
    r.set('wellness', wellness_bytes)

    servers = []
    for index in range(int(servers_num)):
        servers.append(grpc.server(futures.ThreadPoolExecutor(max_workers=10)))
        loadBalancerServer_pb2_grpc.add_ServerServicer_to_server(
            grpc_server.ServerServicer(),
            servers[-1]
        )
        servers[-1].add_insecure_port(f"0.0.0.0:{50051 + index + 1}")
        servers[-1].start()
    time.sleep(2)

    threads = []
    thread = threading.Thread(target=grpc_LoadBalancerServer.LoadBalancerServicer.start, args=(servers_num,))
    thread.start()
    threads.append(thread)

    randomList = []
    clients = []

    for index in range(int(qualitySensors)):
        success = False
        while not success:
            sensorId = random.randint(1, 999)
            if sensorId not in randomList:
                randomList.append(sensorId)
                clients.append(grpc_sensor.Sensor(sensorId=sensorId, sensorType=0))
                success = True

    for index in range(int(pollutionSensors)):
        success = False
        while not success:
            sensorId = random.randint(1, 999)
            if sensorId not in randomList:
                randomList.append(sensorId)
                clients.append(grpc_sensor.Sensor(sensorId=sensorId, sensorType=1))
                success = True

    for client in clients:
        thread = threading.Thread(target=client.start)
        thread.start()
        threads.append(thread)

    processes = []

    for index in range(int(terminals)):
        process = multiprocessing.Process(target=grpc_terminal.send_resultsServicer.run_server,
                                          args=(terminals, servers_num, index + 1,))
        process.start()
        processes.append(process)

    process = multiprocessing.Process(target=grpc_proxy.run_client, args=(terminals, servers_num,))
    process.start()
    processes.append(process)

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        pass

    for process in processes:
        process.terminate()
        process.join()
    for thread in threads:
        thread.join()
    for server in servers:
        server.stop(0)

main()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
