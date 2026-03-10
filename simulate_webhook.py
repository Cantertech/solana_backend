import requests
import json

WEBHOOK_URL = "http://localhost:8000/webhook/helius"

# Simulating a user making a $1,500 DCA Order on Jupiter DCA
dummy_payload = [
    {
        "signature": "3uXqDummySignatureDca123...",
        "feePayer": "CtwUS5C1C8rBty986v8sNqD9CihqjFXvE6AFTtU28uE2",  # Target User
        "accountData": [
            {"account": "DCA265Vj8a9CEuX1eb1LWRnDT7uK6q1xVuB4AQvnE1v"}  # Jupiter DCA Program
        ],
        "nativeTransfers": [],
        "tokenTransfers": [
            {
                "fromUserAccount": "CtwUS5C1C8rBty986v8sNqD9CihqjFXvE6AFTtU28uE2",
                "toUserAccount": "SomeVault...",
                "tokenAmount": 1500.00,  # $1,500 USD equivalent entering DCA protocol
                "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" # USDC Mint
            }
        ]
    }
]

print("Simulating Helius sending an on-chain Webhook to our indexer...")
response = requests.post(WEBHOOK_URL, json=dummy_payload)
print(f"Backend Response: {response.text}")
