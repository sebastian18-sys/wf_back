const express = require('express');
const managerRouter = express.Router();
const { exec, spawn } = require('child_process');
const { promisify } = require('util');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const os = require('os');
const db = require("../../db/conn");
const { storage, upload } = require('../../utils/multer');


function runEscenariosPython(dataprocess) {

    return new Promise((resolve, reject) => {
        const scriptPath = path.resolve(__dirname, '../../../scripts/python/scenarios-opex.py');

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
        const scriptPath = path.resolve(__dirname, '../../../scripts/python/upload-data-capex.py');
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

        })

        py.stdin.write(JSON.stringify({ manifest: serverManifest }));
        py.stdin.end();

    })
}

managerRouter.route('/testdb')
    .get(async (req, res) => {
        try {
            const rows =
                await db.query("SELECT 1 AS ok")
                res.json(rows)

        } catch (error) {
            console.error(`exec error: ${error}`);
            return res.status(500).json({
                message: 'ERROR_CALCULO_ESCENARIOS',
                error: error.message,
            });
        }
    });


managerRouter.route('/scenarios-opex')
    .get(async (req, res) => {

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
    });


managerRouter.route('/scenarios-opex-data')
    .post(async (req, res) => {

        console.log("POST", req.body);

        try {
            const { data } = req.body; // viene del front
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

    });


managerRouter.route('/upload-data-capex')
    .post(upload.any(), async (req, res) => {

        const cleanup = () => {
            if(req._tmpdir) fs.rmSync(req._tmpdir, { recursive: true, force: true });
        }

        try {

            if(!req.body.manifest) {
                cleanup();
                res.status(400).json({"message": "ERROR", "content": "Missing manifest"});
            }

            const clientManifest = JSON.parse(req.body.manifest);

            const mapFieldToPath = Object.fromEntries((req.files || []).map(f => [f.fieldname, f.path]));

            const serverManifest = {
                rq: (clientManifest.rq || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
                oc: (clientManifest.oc || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
                cr: (clientManifest.cr || []).map(f => ({ ...f, path: mapFieldToPath[f.field] })),
                misc: (clientManifest.misc || []).map(f => ({ ...f, path: mapFieldToPath[f.field] }))
            };

            const payload = await runUploadData(serverManifest);
            cleanup();
            console.log("PAYLOAD", payload);
            return res.json(payload);
      
            // const scriptPath = path.resolve(__dirname, '../../../scripts/python/upload-data-capex.py');

            // const py = spawn('python3', ['-u',scriptPath], {
            //     stdio: ['pipe', 'pipe', 'pipe']
            // });

            // console.log("py", py.pid)

            // py.stdin.write(JSON.stringify({ manifest: serverManifest }));
            // py.stdin.end();

            // let out = '', err = ''
            // py.stdout.on('data', (d) => {
            //     const s = d.toString()
            //     out += s
            //     console.log("[PY][STDOUT]", s.trim())
            // });

            // py.stderr.on('data', (d) => {
            //     const s = d.toString()
            //     err += s
            //     console.error("[PY][STDERR]", s.trim())
            // })

            // console.log("py out", out)
            // console.log("py err", err)

            // py.on('close', (code) => {
            //     cleanup();
            //     if(code !== 0) return res.status(500).json({"message": "Python ERROR", "content": err});

            //     try {
            //         const payload = JSON.parse(out);
            //         return res.json({"message": "OK", "content": payload});
            //     } catch (error) {
            //         return res.json({"message": "ERROR PY", "content": err});
            //     }
            // })

        } catch (error) {
            cleanup();
            return res.json({"message": "ERROR GENERAL", "content": error});
        }

            

        // const execAsync = promisify(exec);

        // await execAsync('python3 scripts/python/upload-data-capex.py', async (error, stdout, stderr) => {
        //     if (error) {
        //         console.error(`exec error: ${error}`);
        //         return;
        //     }
        //     console.log(`stdout: ${stdout}`);
        //     console.log(`stderr: ${stderr}`);
        //     // res.send(stdout);
        //     res.send({"message": "OK"});
        // });

        
    });

module.exports = managerRouter;