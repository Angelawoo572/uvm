import json

with open('example.json', 'r') as file:
    data = json.load(file)

print(data["reference"])
print(data["covergroups"][0]["reference"])

def create_bin(signals, states):
    return "hi"

# 

