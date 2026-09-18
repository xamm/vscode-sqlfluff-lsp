import * as path from 'path';
import Mocha = require('mocha');

export async function run(): Promise<void> {
    const mocha = new Mocha({ ui: 'tdd', timeout: 60_000, color: true });
    mocha.addFile(path.resolve(__dirname, 'extension.test.js'));
    await mocha.loadFilesAsync();

    await new Promise<void>((resolve, reject) => {
        mocha.run((failures: number) => {
            if (failures > 0) {
                reject(new Error(`${failures} tests failed`));
                return;
            }
            resolve();
        });
    });
}
