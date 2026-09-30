const pyS = require('../../services/pyServices');
const db = require("../../db/conn");

async function scenariosOpex(req, res) {
    try {
        const py = await pyS.scenariosOpexService()
        res.status(200).json({ ok: true, data: py })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ ok: false, error: 'Error al validar el usuario' })
    }
}

async function scenariosOpexData(req, res) {

    const { data } = req.body; // viene del front

    try {
        const py = await pyS.scenariosOpexDataService(data)
        res.status(200).json({ ok: true, data: py })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ ok: false, error: 'Error al validar el usuario' })
    }
}

async function uploadDataCapex(req, res) {

    const { _tmpdir, manifest, files } = req.body;

    console.log(manifest)
    
    try {
        const py = await pyS.uploadDataCapexService(_tmpdir, manifest, req.files)
        res.status(200).json({ message: "ok", content: py })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ message: "nok", content: 'Error al validar el usuario' })
    }

}

async function testdb(req, res) {
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
}


module.exports = {
    scenariosOpex,
    scenariosOpexData,
    uploadDataCapex,
    testdb
}