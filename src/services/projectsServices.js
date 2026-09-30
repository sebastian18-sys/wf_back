const db = require("../db/conn");

async function getProjectsService() {
    try {
        const projectsData = await db.query(`
            SELECT
                p.project_id,
                p.project_seq,
                p.project_code,
                p.name AS project_name,
                p.year,
                p.typology,
                p.scope_value,
                p.purpose,
                p.jefatura,
                COALESCE(s.name, '') AS sponsors,

                /* avance */
                COALESCE((
                    SELECT ROUND(
                        100 * SUM(
                            CASE
                                WHEN ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                                    AND ps.status = 'DONE'
                                THEN 1 ELSE 0
                            END
                        ) / NULLIF(
                            SUM(
                                CASE
                                    WHEN ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                                    THEN 1 ELSE 0
                                END
                            ),
                            0
                        ),
                        0
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                ), 0) AS progress_pct,

                /* stand by */
                COALESCE((
                    SELECT MAX(
                        CASE
                            WHEN ms.code = 'STAND_BY' AND ps.status IN ('IN_PROGRESS', 'DONE')
                            THEN 1 ELSE 0
                        END
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                ), 0) AS is_standby,

                /* código de etapa actual */
                COALESCE((
                    SELECT ms.code
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                    ORDER BY
                        CASE
                            WHEN ps.status = 'IN_PROGRESS' THEN 1
                            WHEN ps.status = 'DONE' THEN 2
                            WHEN ps.status = 'PENDING' THEN 3
                            ELSE 4
                        END,
                        CASE
                            WHEN ps.status = 'DONE' THEN -ms.stage_order
                            ELSE ms.stage_order
                        END
                    LIMIT 1
                ), 'INICIATIVA') AS current_stage_code,

                /* objeto de etapa actual */
                COALESCE((
                    SELECT JSON_OBJECT(
                        'stage_id', ms.stage_id,
                        'code', ms.code,
                        'name', ms.name,
                        'stage_order', ms.stage_order,
                        'planned_start_date', DATE_FORMAT(ps.planned_start_date, '%Y-%m-%d'),
                        'planned_end_date', DATE_FORMAT(ps.planned_end_date, '%Y-%m-%d'),
                        'actual_start_date', DATE_FORMAT(ps.actual_start_date, '%Y-%m-%d'),
                        'actual_end_date', DATE_FORMAT(ps.actual_end_date, '%Y-%m-%d'),
                        'status', ps.status,
                        'ui_status',
                            CASE
                                WHEN ps.status = 'DONE' THEN 'done'
                                WHEN ps.status = 'IN_PROGRESS'
                                    AND ps.planned_end_date IS NOT NULL
                                    AND CURDATE() > ps.planned_end_date THEN 'risk'
                                WHEN ps.status = 'IN_PROGRESS' THEN 'actual'
                                ELSE 'planned'
                            END
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                    ORDER BY
                        CASE
                            WHEN ps.status = 'IN_PROGRESS' THEN 1
                            WHEN ps.status = 'DONE' THEN 2
                            WHEN ps.status = 'PENDING' THEN 3
                            ELSE 4
                        END,
                        CASE
                            WHEN ps.status = 'DONE' THEN -ms.stage_order
                            ELSE ms.stage_order
                        END
                    LIMIT 1
                ), JSON_OBJECT()) AS current_stage,

                /* tipos */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'project_type_id', pt.project_type_id,
                            'code', pt.code,
                            'name', pt.name
                        )
                    )
                    FROM project_project_types ppt
                    INNER JOIN project_types pt
                        ON pt.project_type_id = ppt.project_type_id
                    WHERE ppt.project_id = p.project_id
                ), JSON_ARRAY()) AS project_types,

                /* usuarios */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'user_id', pu.user_id,
                            'full_name', CONCAT(u.first_name,' ',u.last_name),
                            'email', u.email,
                            'project_role', pu.project_role,
                            'area', pu.area,
                            'project_type', pt.name,
                            'joined_at', DATE_FORMAT(pu.joined_at, '%Y-%m-%d %H:%i:%s')
                        )
                    )
                    FROM project_users pu
                    INNER JOIN project_types pt
                        ON pt.project_type_id = pu.project_type_id
                    INNER JOIN users u
                        ON u.user_id = pu.user_id
                    WHERE pu.project_id = p.project_id
                ), JSON_ARRAY()) AS users,

                /* stages del timeline */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'stage_id', ms.stage_id,
                            'code', ms.code,
                            'name', ms.name,
                            'stage_order', ms.stage_order,
                            'planned_start_date', DATE_FORMAT(ps.planned_start_date, '%Y-%m-%d'),
                            'planned_end_date', DATE_FORMAT(ps.planned_end_date, '%Y-%m-%d'),
                            'actual_start_date', DATE_FORMAT(ps.actual_start_date, '%Y-%m-%d'),
                            'actual_end_date', DATE_FORMAT(ps.actual_end_date, '%Y-%m-%d'),
                            'status', ps.status,
                            'ui_status',
                                CASE
                                    WHEN ps.status = 'DONE' THEN 'done'
                                    WHEN ps.status = 'IN_PROGRESS'
                                        AND ps.planned_end_date IS NOT NULL
                                        AND CURDATE() > ps.planned_end_date THEN 'risk'
                                    WHEN ps.status = 'IN_PROGRESS' THEN 'actual'
                                    ELSE 'planned'
                                END
                        )
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                ), JSON_ARRAY()) AS stages

            FROM projects p
            LEFT JOIN sponsors s
                ON s.sponsor_id = p.sponsor_id
            ORDER BY p.year DESC, p.project_seq DESC;

        `)
        return projectsData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

async function getProjectsInfoByIdService(id) {
    try {
        const projectsData = await db.query(
            `
            SELECT
                p.project_id,
                p.project_seq,
                p.project_code,
                p.name AS project_name,
                p.year,
                p.typology,
                p.scope_value,
                p.purpose,
                p.jefatura,
                COALESCE(s.name, '') AS sponsors,

                /* avance */
                COALESCE((
                    SELECT ROUND(
                        100 * SUM(
                            CASE
                                WHEN ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                                    AND ps.status = 'DONE'
                                THEN 1 ELSE 0
                            END
                        ) / NULLIF(
                            SUM(
                                CASE
                                    WHEN ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                                    THEN 1 ELSE 0
                                END
                            ),
                            0
                        ),
                        0
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                ), 0) AS progress_pct,

                /* stand by */
                COALESCE((
                    SELECT MAX(
                        CASE
                            WHEN ms.code = 'STAND_BY' AND ps.status IN ('IN_PROGRESS', 'DONE')
                            THEN 1 ELSE 0
                        END
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                ), 0) AS is_standby,

                /* código de etapa actual */
                COALESCE((
                    SELECT ms.code
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                    ORDER BY
                        CASE
                            WHEN ps.status = 'IN_PROGRESS' THEN 1
                            WHEN ps.status = 'DONE' THEN 2
                            WHEN ps.status = 'PENDING' THEN 3
                            ELSE 4
                        END,
                        CASE
                            WHEN ps.status = 'DONE' THEN -ms.stage_order
                            ELSE ms.stage_order
                        END
                    LIMIT 1
                ), 'INICIATIVA') AS current_stage_code,

                /* objeto de etapa actual */
                COALESCE((
                    SELECT JSON_OBJECT(
                        'stage_id', ms.stage_id,
                        'code', ms.code,
                        'name', ms.name,
                        'stage_order', ms.stage_order,
                        'planned_start_date', DATE_FORMAT(ps.planned_start_date, '%Y-%m-%d'),
                        'planned_end_date', DATE_FORMAT(ps.planned_end_date, '%Y-%m-%d'),
                        'actual_start_date', DATE_FORMAT(ps.actual_start_date, '%Y-%m-%d'),
                        'actual_end_date', DATE_FORMAT(ps.actual_end_date, '%Y-%m-%d'),
                        'status', ps.status,
                        'ui_status',
                            CASE
                                WHEN ps.status = 'DONE' THEN 'done'
                                WHEN ps.status = 'IN_PROGRESS'
                                    AND ps.planned_end_date IS NOT NULL
                                    AND CURDATE() > ps.planned_end_date THEN 'risk'
                                WHEN ps.status = 'IN_PROGRESS' THEN 'actual'
                                ELSE 'planned'
                            END
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                    ORDER BY
                        CASE
                            WHEN ps.status = 'IN_PROGRESS' THEN 1
                            WHEN ps.status = 'DONE' THEN 2
                            WHEN ps.status = 'PENDING' THEN 3
                            ELSE 4
                        END,
                        CASE
                            WHEN ps.status = 'DONE' THEN -ms.stage_order
                            ELSE ms.stage_order
                        END
                    LIMIT 1
                ), JSON_OBJECT()) AS current_stage,

                /* tipos */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'project_type_id', pt.project_type_id,
                            'code', pt.code,
                            'name', pt.name
                        )
                    )
                    FROM project_project_types ppt
                    INNER JOIN project_types pt
                        ON pt.project_type_id = ppt.project_type_id
                    WHERE ppt.project_id = p.project_id
                ), JSON_ARRAY()) AS project_types,

                /* usuarios */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'user_id', pu.user_id,
                            'full_name', CONCAT(u.first_name,' ',u.last_name),
                            'email', u.email,
                            'project_role', pu.project_role,
                            'area', pu.area,
                            'project_type', pt.name,
                            'joined_at', DATE_FORMAT(pu.joined_at, '%Y-%m-%d %H:%i:%s')
                        )
                    )
                    FROM project_users pu
                    INNER JOIN project_types pt
                        ON pt.project_type_id = pu.project_type_id
                    INNER JOIN users u
                        ON u.user_id = pu.user_id
                    WHERE pu.project_id = p.project_id
                ), JSON_ARRAY()) AS users,

                /* stages del timeline */
                COALESCE((
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'stage_id', ms.stage_id,
                            'code', ms.code,
                            'name', ms.name,
                            'stage_order', ms.stage_order,
                            'planned_start_date', DATE_FORMAT(ps.planned_start_date, '%Y-%m-%d'),
                            'planned_end_date', DATE_FORMAT(ps.planned_end_date, '%Y-%m-%d'),
                            'actual_start_date', DATE_FORMAT(ps.actual_start_date, '%Y-%m-%d'),
                            'actual_end_date', DATE_FORMAT(ps.actual_end_date, '%Y-%m-%d'),
                            'status', ps.status,
                            'ui_status',
                                CASE
                                    WHEN ps.status = 'DONE' THEN 'done'
                                    WHEN ps.status = 'IN_PROGRESS'
                                        AND ps.planned_end_date IS NOT NULL
                                        AND CURDATE() > ps.planned_end_date THEN 'risk'
                                    WHEN ps.status = 'IN_PROGRESS' THEN 'actual'
                                    ELSE 'planned'
                                END
                        )
                    )
                    FROM project_stages ps
                    INNER JOIN methodology_stages ms
                        ON ms.stage_id = ps.stage_id
                    WHERE ps.project_id = p.project_id
                    AND ms.code IN ('INICIATIVA', 'PLANIFICACION', 'EJECUCION', 'CIERRE')
                ), JSON_ARRAY()) AS stages

            FROM projects p
            LEFT JOIN sponsors s
                ON s.sponsor_id = p.sponsor_id
            WHERE p.project_code = ?
            `
        , [id])
        return projectsData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

module.exports = {
    getProjectsService,
    getProjectsInfoByIdService
}