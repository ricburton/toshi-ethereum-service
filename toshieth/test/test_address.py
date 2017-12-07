import asyncio
import os
import time
import random
import binascii
from tornado.escape import json_decode, json_encode
from tornado.testing import gen_test
from tornado.platform.asyncio import to_asyncio_future

from toshieth.test.base import EthServiceBaseTest, requires_task_manager, requires_full_stack
from toshi.test.database import requires_database
from toshi.test.redis import requires_redis
from toshi.test.ethereum.parity import requires_parity, FAUCET_PRIVATE_KEY, FAUCET_ADDRESS
from toshi.analytics import encode_id
from toshi.request import sign_request
from toshi.ethereum.utils import data_decoder, data_encoder
from toshi.ethereum.tx import sign_transaction, decode_transaction, signature_from_transaction, encode_transaction, DEFAULT_STARTGAS, DEFAULT_GASPRICE
from toshi.utils import parse_int

TEST_PRIVATE_KEY = data_decoder("0xe8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35")
TEST_ADDRESS = "0x056db290f8ba3250ca64a45d16284d04bc6f5fbf"

TEST_PRIVATE_KEY_2 = data_decoder("0x0ffdb88a7a0a40831ca0b19bd31f3f6085764ef8b7db1bd6b57072e5eaea24ff")
TEST_ADDRESS_2 = "0x35351b44e03ec8515664a955146bf9c6e503a381"

def random_hash():
    return "0x" + binascii.b2a_hex(os.urandom(32)).decode('utf-8')
def random_address():
    return "0x" + binascii.b2a_hex(os.urandom(20)).decode('utf-8')

class TransactionListTest(EthServiceBaseTest):

    @gen_test(timeout=15)
    @requires_full_stack
    async def test_transaction_list(self):

        for i in range(5):
            await self.send_tx(FAUCET_PRIVATE_KEY, TEST_ADDRESS, random.randint(1, 100) ** 16)

        await self.send_tx(TEST_PRIVATE_KEY, TEST_ADDRESS_2, 10 ** 15)

        resp = await self.fetch("/address/{}".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 200)
        body = json_decode(resp.body)
        self.assertIn('transactions', body)
        self.assertEqual(len(body['transactions']), 6)

    @gen_test
    @requires_database
    async def test_status_filtering(self):
        async with self.pool.acquire() as con:
            confirmed = True
            for i in range(10):
                await con.execute("INSERT INTO transactions (hash, from_address, to_address, nonce, value, status) VALUES ($1, $2, $3, $4, $5, $6)", random_hash(), TEST_ADDRESS, random_address(), random.randint(0, 100), hex(random.randint(1, 100) ** 16), 'confirmed' if confirmed else 'unconfirmed')
                confirmed = not confirmed

        resp = await self.fetch("/address/{}?status=unconfirmed".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 200)
        body = json_decode(resp.body)
        self.assertIn('transactions', body)
        self.assertEqual(len(body['transactions']), 5)
        for tx in body['transactions']:
            self.assertEqual(tx['status'], 'unconfirmed')

        resp = await self.fetch("/address/{}?status=confirmed".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 200)
        body = json_decode(resp.body)
        self.assertIn('transactions', body)
        self.assertEqual(len(body['transactions']), 5)
        for tx in body['transactions']:
            self.assertEqual(tx['status'], 'confirmed')

    @gen_test
    @requires_database
    async def test_direction_filtering(self):
        async with self.pool.acquire() as con:
            out = True
            for i in range(10):
                await con.execute("INSERT INTO transactions (hash, from_address, to_address, nonce, value, status) VALUES ($1, $2, $3, $4, $5, $6)", random_hash(), TEST_ADDRESS if out else random_hash(), random_address() if out else TEST_ADDRESS, random.randint(0, 100), hex(random.randint(1, 100) ** 16), 'confirmed')
                out = not out

        resp = await self.fetch("/address/{}?direction=in".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 200)
        body = json_decode(resp.body)
        self.assertIn('transactions', body)
        self.assertEqual(len(body['transactions']), 5)
        for tx in body['transactions']:
            self.assertNotEqual(tx['from'], TEST_ADDRESS)
            self.assertEqual(tx['to'], TEST_ADDRESS)

        resp = await self.fetch("/address/{}?direction=out".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 200)
        body = json_decode(resp.body)
        self.assertIn('transactions', body)
        self.assertEqual(len(body['transactions']), 5)
        for tx in body['transactions']:
            self.assertEqual(tx['from'], TEST_ADDRESS)
            self.assertNotEqual(tx['to'], TEST_ADDRESS)

    @gen_test
    @requires_database
    async def test_offset_limit(self):
        async with self.pool.acquire() as con:
            out = True
            for i in range(20):
                await con.execute("INSERT INTO transactions (hash, from_address, to_address, nonce, value, status) VALUES ($1, $2, $3, $4, $5, $6)", random_hash(), TEST_ADDRESS if out else random_hash(), random_address() if out else TEST_ADDRESS, i, hex(random.randint(1, 100) ** 16), 'confirmed')
                out = not out

        nonce = 19
        for offset in range(0, 20, 5):
            resp = await self.fetch("/address/{}?offset={}&limit={}".format(TEST_ADDRESS, offset, 5))
            self.assertResponseCodeEqual(resp, 200)
            body = json_decode(resp.body)
            self.assertIn('transactions', body)
            self.assertEqual(len(body['transactions']), 5)
            for tx in body['transactions']:
                self.assertEqual(int(tx['nonce'], 16), nonce)
                nonce -= 1

    @gen_test
    @requires_database
    async def test_bad_values(self):
        resp = await self.fetch("/address/abc")
        self.assertResponseCodeEqual(resp, 404)

        resp = await self.fetch("/address/{}?offset=a".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 400)

        resp = await self.fetch("/address/{}?limit=a".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 400)

        resp = await self.fetch("/address/{}?status=a".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 400)

        resp = await self.fetch("/address/{}?direction=a".format(TEST_ADDRESS))
        self.assertResponseCodeEqual(resp, 400)
