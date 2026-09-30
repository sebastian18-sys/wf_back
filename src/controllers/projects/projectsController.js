const projects = require('../../services/projectsServices');

async function getProjects(req, res) {
    try {
        const data = await projects.getProjectsService()
        res.status(200).json({ message: "ok", content: data })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ message: "nok", content: { error: error.message } })
    }
}

async function getProjectsInfoById(req, res) {
    try {
        const id = req.params.id
        if(!id) return res.status(400).json({ message: "error", content: { error: 'Missing id' } })

        const data = await projects.getProjectsInfoByIdService(id)
        res.status(200).json({ message: "ok", content: data })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ message: "nok", content: { error: error.message } })
    }
}

module.exports = {
    getProjects,
    getProjectsInfoById
}