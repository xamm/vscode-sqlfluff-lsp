import * as assert from 'assert';
import * as path from 'path';
import * as vscode from 'vscode';

import { openSqlDocument, restartAndAwaitRepublish, waitForDiagnostics } from './helpers';

const workspacePath = process.env.SQLFLUFF_TEST_WORKSPACE;
if (!workspacePath) {
    throw new Error('SQLFLUFF_TEST_WORKSPACE is not set');
}

const WORKSPACE = workspacePath;
const QUERY_URI = vscode.Uri.file(path.join(WORKSPACE, 'query.sql'));
const ORIGINAL = 'select a,b from t\n';
const FORMATTED = 'select\n    a,\n    b\nfrom t\n';

suite('SQLFluff extension host', () => {
    test('extension activates and publishes sqlfluff diagnostics', async () => {
        const extension = vscode.extensions.getExtension('xsw.vscode-sqlfluff-lsp');
        assert.ok(extension);
        await extension.activate();

        await openSqlDocument(QUERY_URI);
        const diagnostics = await waitForDiagnostics(QUERY_URI, 30_000);
        assert.ok(diagnostics.length > 0);
        assert.ok(diagnostics.every((diagnostic) => diagnostic.source === 'sqlfluff'));
        assert.ok(diagnostics.some((diagnostic) => new Set(['LT01', 'LT09']).has(String(diagnostic.code))));
        assert.ok(
            diagnostics.every(
                (diagnostic) => diagnostic.range.start.line >= 0 && diagnostic.range.start.character >= 0,
            ),
        );
    });

    test('formats a SQL document through the VS Code provider', async () => {
        const document = await openSqlDocument(QUERY_URI);
        const edits = await vscode.commands.executeCommand<vscode.TextEdit[] | undefined>(
            'vscode.executeFormatDocumentProvider',
            QUERY_URI,
            { tabSize: 4, insertSpaces: true },
        );

        assert.ok(edits);
        assert.ok(edits.length > 0);
        const formattedText = [...edits]
            .sort((left, right) => document.offsetAt(right.range.start) - document.offsetAt(left.range.start))
            .reduce((text, edit) => {
                const start = document.offsetAt(edit.range.start);
                const end = document.offsetAt(edit.range.end);
                return text.slice(0, start) + edit.newText + text.slice(end);
            }, document.getText());
        assert.strictEqual(formattedText, FORMATTED);
        assert.notStrictEqual(formattedText, document.getText());
    });

    test('sqlfluff.restart keeps the new client live', async () => {
        const document = await openSqlDocument(QUERY_URI);
        await waitForDiagnostics(QUERY_URI, 30_000);

        await vscode.commands.executeCommand('sqlfluff.restart');
        await restartAndAwaitRepublish(QUERY_URI, 45_000);

        const formattedEdit = new vscode.WorkspaceEdit();
        formattedEdit.replace(QUERY_URI, new vscode.Range(0, 0, document.lineCount, 0), FORMATTED);
        assert.ok(await vscode.workspace.applyEdit(formattedEdit));
        await waitForDiagnostics(QUERY_URI, 30_000, (diagnostics) => diagnostics.length === 0);

        const originalEdit = new vscode.WorkspaceEdit();
        originalEdit.replace(QUERY_URI, new vscode.Range(0, 0, document.lineCount, 0), ORIGINAL);
        assert.ok(await vscode.workspace.applyEdit(originalEdit));
        await waitForDiagnostics(QUERY_URI, 30_000);
    });

    test('configuration changes restart the server', async () => {
        await openSqlDocument(QUERY_URI);
        await waitForDiagnostics(QUERY_URI, 30_000);

        const configuration = vscode.workspace.getConfiguration('sqlfluff');
        try {
            await configuration.update('dialect', 'postgres', vscode.ConfigurationTarget.Workspace);
            await restartAndAwaitRepublish(QUERY_URI, 45_000);
            const diagnostics = await waitForDiagnostics(QUERY_URI, 30_000);
            assert.ok(diagnostics.length > 0);
            assert.ok(diagnostics.every((diagnostic) => diagnostic.source === 'sqlfluff'));
        } finally {
            await configuration.update('dialect', undefined, vscode.ConfigurationTarget.Workspace);
        }
    });
});
