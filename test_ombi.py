import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession() as s:
        async with s.get(
            'http://192.168.1.5:3579/api/v1/Search/movie/dune',
            headers={'ApiKey': '5becafb1e9914d9c84d60946d7f4600e'}
        ) as r:
            data = await r.json()
            print(json.dumps(data, indent=2))

asyncio.run(test())
