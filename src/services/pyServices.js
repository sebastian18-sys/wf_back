const { exec, spawn } = require('child_process');
const { promisify } = require('util');
const path = require('path');
const fs = require('fs');


function runEscenariosPython(dataprocess) {

    return new Promise((resolve, reject) => {
        const scriptPath = path.resolve(__dirname, '../../scripts/python/scenarios-opex.py');

        const py = spawn('python3', ['-u',scriptPath], {
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        py.stdout.on('data', chunk => {
            stdout += chunk.toString();
        });

        py.stderr.on('data', chunk => {
            stderr += chunk.toString();
        });

        py.on('error', (err) => {
            reject(new Error(`Error al ejecutar Python: ${err.message}`));
        });

        py.on('close', (code) => {
            // 1) Si Python terminó mal -> error
            if (code !== 0) {
                return reject(
                    new Error(`Python devolvió código de salida: ${code}\nSalida: ${stderr}`)
                );
            }

            // 2) Si terminó bien (code === 0) pero hubo stderr, lo logueamos como warning, NO rompemos
            if (stderr.trim()) {
                console.warn('[PYTHON WARNING]', stderr.trim());
            }

            // 3) Validar salida
            if (!stdout.trim()) {
                return reject(new Error('Python devolvió salida vacía'));
            }

            try {
                const payload = JSON.parse(stdout);
                return resolve(payload);
            } catch (e) {
                return reject(
                    new Error(
                        `Python devolvió JSON inválido: ${e.message}\nSalida: ${stdout}`
                    )
                );
            }
        });

        // Enviar dataprocess por stdin
        py.stdin.write(JSON.stringify(dataprocess));
        py.stdin.end();
    });
}

function runUploadData(serverManifest) {
    return new Promise((resolve, reject) => {
        const scriptPath = path.resolve(__dirname, '../../scripts/python/upload-data-capex.py');
        const py = spawn('python3', ['-u',scriptPath], {
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        py.stdout.on('data', chunk => {
            stdout += chunk.toString();
        });

        py.stderr.on('data', chunk => {
            stderr += chunk.toString();
        });

        py.on('error', (err) => {
            reject(new Error(`Error al ejecutar Python: ${err.message}`));
        });

        py.on('close', (code) => {
            // cleanup();

            if (code !== 0) {
                return reject(
                    new Error(`Python devolvió código de salida: ${code}\nSalida: ${stderr}`)
                );
            }

            if (stderr.trim()) {
                console.warn('[PYTHON WARNING]', stderr.trim());
            }

            // 3) Validar salida
            if (!stdout.trim()) {
                return reject(new Error('Python devolvió salida vacía'));
            }

             try {
                const payload = JSON.parse(stdout);
                return resolve(payload);
            } catch (e) {
                return reject(
                    new Error(
                        `Python devolvió JSON inválido: ${e.message}\nSalida: ${stdout}`
                    )
                );
            }

        })

        py.stdin.write(JSON.stringify({ manifest: serverManifest }));
        py.stdin.end();

    })
}


async function scenariosOpexService() {
    const execAsync = promisify(exec);
    console.log('run-python!!!');
    try {
        const { stdout, stderr } = await execAsync('python3 scripts/python/scenarios-opex.py');

        if(stdout) {
            console.log(`stdout: ${stdout}`);
            // return;
        }
        if(stderr) {
            console.error(`exec error: ${stderr}`);
            return;
        }

        const payload = JSON.parse(stdout);
        res.send({"message": "OK", "content": payload});

    } catch (error) {
        console.error(`exec error: ${error}`);
    }
}


async function scenariosOpexDataService(data) {
    try {
        const payload = await runEscenariosPython(data);
        console.log("PAYLOAD", payload);
        return res.json(payload);
    } catch (err) {
        console.error('Error en /escenarios:', err.message);
        return res.status(500).json({
            message: 'ERROR_CALCULO_ESCENARIOS',
            error: err.message,
        });
    }
}

async function uploadDataCapexService(_tmpdir, manifest, files) {

    const cleanup = () => {
        if(_tmpdir) fs.rmSync(_tmpdir, { recursive: true, force: true });
    }

    try {
        if(!manifest) {
            cleanup();
            throw new Error('Missing manifest');
        }
        const clientManifest = JSON.parse(manifest);

        const mapFieldToPath = Object.fromEntries((files || []).map(f => [f.fieldname, f.path]));

        const serverManifest = {
            rq: (clientManifest.rq || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
            oc: (clientManifest.oc || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
            cr: (clientManifest.cr || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
            misc: (clientManifest.misc || []).map(f => ({ ...f, path: mapFieldToPath[f.field] }))
        };
        const payload = await runUploadData(serverManifest);
        cleanup();
        console.log("PAYLOAD", payload);
        // return 
        // res not working i need return payload
        return payload
        // return json(payload);
    } catch (error) {
        cleanup();
        throw new Error(error)
        // return json({"message": "ERROR GENERAL", "content": error});
    }
}


module.exports = {
	scenariosOpexService,
    scenariosOpexDataService,
    uploadDataCapexService
}