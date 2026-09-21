import * as assert from 'assert';
import * as path from 'path';
import * as vscode from 'vscode';

import { openSqlDocument, waitForDiagnostics } from './helpers';

const workspacePath = process.env.SQLFLUFF_TEST_WORKSPACE;
if (!workspacePath) {
    throw new Error('SQLFLUFF_TEST_WORKSPACE is not set');
}

const WORKSPACE = workspacePath;
const MODEL_URI = vscode.Uri.file(path.join(WORKSPACE, 'models', 'stg_customers.sql'));

suite('SQLFluff dbt extension host', () => {
    test('publishes dbt diagnostics', async () => {
        await openSqlDocument(MODEL_URI);
        const diagnostics = await waitForDiagnostics(MODEL_URI, 90_000);

        assert.ok(diagnostics.length > 0);
        assert.ok(diagnostics.every((diagnostic) => diagnostic.source === 'sqlfluff'));
        assert.ok(diagnostics.some((diagnostic) => new Set(['LT01', 'LT09']).has(String(diagnostic.code))));
        assert.ok(
            diagnostics.every(
                (diagnostic) => diagnostic.range.start.line >= 0 && diagnostic.range.start.character >= 0,
            ),
        );
    });

    test('formats dbt SQL while preserving Jinja', async () => {
        await openSqlDocument(MODEL_URI);
        const edits = await vscode.commands.executeCommand<vscode.TextEdit[] | undefined>(
            'vscode.executeFormatDocumentProvider',
            MODEL_URI,
            { tabSize: 4, insertSpaces: true },
        );

        assert.ok(edits);
        assert.ok(edits.length > 0);
        const document = await vscode.workspace.openTextDocument(MODEL_URI);
        const formattedText = [...edits]
            .sort((left, right) => document.offsetAt(right.range.start) - document.offsetAt(left.range.start))
            .reduce((text, edit) => {
                const start = document.offsetAt(edit.range.start);
                const end = document.offsetAt(edit.range.end);
                return text.slice(0, start) + edit.newText + text.slice(end);
            }, document.getText());
        assert.ok(formattedText.startsWith('select\n'));
        assert.ok(formattedText.includes("{{ ref('raw_customers') }}"));
    });
});
