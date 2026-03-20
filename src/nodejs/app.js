const dotenv = require('dotenv');
dotenv.config();
const express = require('express');
const app = express()
const PORT = process.env.PORT || 3000;
app.use(express.json())

const header = {
    "X-Mode": process.env.MODE,
}

app.get('/', (req, res)=>{
    res.set(header)

    res.status(200).json({
        message: "Welcome to SwiftDeploy CLI",
        current_mode : process.env.MODE,
        version: process.env.VERSION,
        timestamp: new Date().toLocaleString()

    })
    console.log(res.getHeaders())
})

app.get('/healthz', (req, res)=>{
    res.set(header)
    res.status(200).json({
        status: "ok",
        uptime: process.uptime().toLocaleString(),
        timestamp: new Date().toLocaleString()
    })  
})

app.get('/metrics', (req, res)=>{})

app.post('/chaos', (req,res)=>{
    req.set(header)
    if (process.env.MODE !== 'canary') {
        return res.status(403).json({ error: 'chaos only available in canary mode' });
    }
    const {mode, duration, rate} = req.body

    if(mode === "slow"){
        setTimeout(()=>{
            res.status(200).json({
                message: `Response delayed by ${duration} ms`
            })
        }, duration)
    }

    if(mode === "error"){
        res.status(500).json({
            message: "Simulated error response"
        })
    }

    if (mode.mode === "recover"){
        res.status(200).json({
            message: "System recovered to normal state"
        })
    }

})


app.listen(PORT, "0.0.0.0",  ()=>{
    console.log(`Server is running on port ${PORT}`)
})





































// function times(){
//     const time1 = new Date().toISOString();
//     const time2 = new Date().toLocaleString();
//     const time3 = new Date().getTime();
//     const uptime = process.uptime().toLocaleString()
//     console.log({time1, time2, time3, uptime})
// }

// times();


// let chaosState = { mode: 'none', rate: 0, duration: 0 };

// app.use(async (req, res, next) => {
//   if (chaosState.mode === 'global-slow') {
//     await delay(chaosState.duration);
//   }
//   next();
// });