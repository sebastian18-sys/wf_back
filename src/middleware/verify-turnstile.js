// const fetch = require('node-fetch');

const verifyTurnstile = async (req, res, next) => {
    const { token } = req.body;

    console.log("TOKEN", token);

    if (!token) {
        return res.status(400).json({ message: "Missing token" });
    }

    const secret = process.env.TURNSTILE_SECRET_KEY;
    console.log("SECRET", secret);

    const body = new URLSearchParams({
        secret,
        response: token,
    });

    try {
        // const response = await fetch(
        //     `https://challenges.cloudflare.com/turnstile/v0/siteverify?secret=${secret}&response=${token}`
        // );
        const response = await fetch(
            `https://challenges.cloudflare.com/turnstile/v0/siteverify`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body,
            }
        );
        
        const data = await response.json();

        if (data.success) {
            return next();
        }

        return res.status(401).json({ message: "Invalid token" });
    } catch (error) {
        console.error(error);
        return res.status(500).json({ message: "Internal server error" });
    }
};

module.exports = { verifyTurnstile };