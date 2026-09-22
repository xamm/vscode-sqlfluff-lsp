import * as fs from 'fs';
import * as fsExtra from 'fs-extra';
import { runTests, runVSCodeCommand } from '@vscode/test-electron';
import * as os from 'os';
import * as path from 'path';

async function makeWorkspace(fixtureDirectory: string, python: string): Promise<string> {
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'sqlfluff-vscode-test-'));
    await fsExtra.copy(fixtureDirectory, workspace);
    fsExtra.ensureDirSync(path.join(workspace, '.vscode'));
    fs.writeFileSync(
        path.join(workspace, '.vscode', 'settings.json'),
        `${JSON.stringify({ ['sqlfluff.interpreter']: [python] }, null, 2)}\n`,
    );
    return workspace;
}

async function main(): Promise<void> {
    const repoRoot = path.resolve(__dirname, '..', '..');
    const defaultPython = path.join(
        repoRoot,
        '.venv',
        process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python',
    );
    const python = process.env.SQLFLUFF_TEST_PYTHON ?? defaultPython;
    if (!fs.existsSync(python)) {
        throw new Error(
            `Python interpreter not found at ${python}; run: uv sync --extra dbt --group test (or set SQLFLUFF_TEST_PYTHON)`,
        );
    }

    const plainFixture = path.join(repoRoot, 'src', 'test', 'workspace', 'plain');
    const dbtFixture = path.join(repoRoot, 'src', 'test', 'python_tests', 'test_data', 'dbt_project');
    const plainWorkspace = await makeWorkspace(plainFixture, python);
    const dbtWorkspace = await makeWorkspace(dbtFixture, python);

    console.log('Installing ms-python.python in the isolated VS Code test instance...');
    await runVSCodeCommand(['--install-extension', 'ms-python.python']);

    console.log('Running plain SQL extension-host tests...');
    await runTests({
        extensionDevelopmentPath: repoRoot,
        extensionTestsPath: path.join(repoRoot, 'out', 'test', 'suite', 'plain.js'),
        launchArgs: [plainWorkspace],
        extensionTestsEnv: { ['SQLFLUFF_TEST_WORKSPACE']: plainWorkspace },
    });

    console.log('Running dbt extension-host tests...');
    await runTests({
        extensionDevelopmentPath: repoRoot,
        extensionTestsPath: path.join(repoRoot, 'out', 'test', 'suite', 'dbt.js'),
        launchArgs: [dbtWorkspace],
        extensionTestsEnv: { ['SQLFLUFF_TEST_WORKSPACE']: dbtWorkspace },
    });
}

main().catch((error: unknown) => {
    process.exitCode = 1;
    console.error('VS Code extension tests failed:', error);
});
