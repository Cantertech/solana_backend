import { Connection, PublicKey } from '@solana/web3.js';
import bs58 from 'bs58';

async function testJup() {
    try {
        const address = "CtwUS5C1C8rBty986v8sNqD9CihqjFXvE6AFTtU28uE2"; // Replace with a JUP staker if known
        const JUP_LOCKER = new PublicKey('voTpe3tHQ7AjQHMapgKep266Kf1eKVtPZcGHpdtGtoA');
        const userPubkey = new PublicKey(address);

        const [escrowKey] = PublicKey.findProgramAddressSync(
            [Buffer.from('Escrow'), JUP_LOCKER.toBuffer(), userPubkey.toBuffer()],
            new PublicKey('GovaE4iu227SRtpjqKzGcCj5zRkHDr9NtxKzU2o3aM6M')
        );

        console.log("Escrow", escrowKey.toBase58());
        const connection = new Connection("https://api.mainnet-beta.solana.com");
        const info = await connection.getAccountInfo(escrowKey);
        if (info) {
            console.log("Got info! Length:", info.data.length);
            const amount = info.data.readBigUInt64LE(72);
            console.log("Staked JUP:", Number(amount) / 1000000);
        } else {
            console.log("No info found!");
        }
    } catch (e) {
        console.error(e)
    }
}
testJup();
