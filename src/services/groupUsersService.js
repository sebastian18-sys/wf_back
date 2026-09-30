const db = require("../db/conn");

async function getResponsiblesService() {
    try {
        const users = await db.query(`
            SELECT
                user_id AS id,
                username,
                first_name,
                last_name,
                email,
                job_title
            FROM users
            WHERE is_active = 1
            ORDER BY first_name, last_name
        `)

        const groups = await db.query(`
            SELECT
                g.group_id AS id,
                g.group_code,
                g.group_name,
                g.description,
                COUNT(gm.user_id) AS member_count
            FROM user_groups g
            LEFT JOIN user_group_members gm
                ON gm.group_id = g.group_id
            WHERE g.is_active = 1
            GROUP BY
                g.group_id,
                g.group_code,
                g.group_name,
                g.description
            ORDER BY g.group_name
        `)

        const groupMembers = await db.query(`
            SELECT
                gm.group_id,
                gm.user_id
            FROM user_group_members gm
            INNER JOIN users u
                ON u.user_id = gm.user_id
            WHERE u.is_active = 1
            ORDER BY gm.group_id, gm.user_id
        `)

        const membersByGroup = new Map()

        for (const member of groupMembers) {
            const groupId = String(member.group_id)

            if (!membersByGroup.has(groupId)) {
                membersByGroup.set(groupId, [])
            }

            membersByGroup
                .get(groupId)
                .push(String(member.user_id))
        }

        return {
            users: users.map(user => ({
                type: "USER",
                id: user.id,
                username: user.username,
                name: `${user.first_name} ${user.last_name}`.trim(),
                email: user.email,
                job_title: user.job_title
            })),

            groups: groups.map(group => ({
                type: "GROUP",
                id: group.id,
                code: group.group_code,
                name: group.group_name,
                description: group.description,
                member_count: Number(group.member_count),
                member_ids:
                    membersByGroup.get(
                        String(group.id)
                    ) || []
            }))
        }

    } catch (error) {
        console.error(`exec error: ${error}`)
        return { error: error.message }
    }
}

module.exports = {
    getResponsiblesService
};