<?php

$toast_message = "";
$toast_type = "ok";

$message = $_POST['message'] ?? '';

// set correct path to python script
if (isset($_POST['send_message']) && $message != '') {
    $cmd = "python3 /opt/meshtastic/message2mqtt.py " . escapeshellarg($message);
    exec($cmd . " > /dev/null 2>&1");
    $toast_message = "Messaggio inviato";
}

if (isset($_POST['send_nodeinfo'])) {
    $cmd = "python3 /opt/meshtastic/message2mqtt.py -i";
    exec($cmd . " > /dev/null 2>&1");
    $toast_message = "Node Info inviato";
}

?>

<!DOCTYPE html>
<html lang="it">
<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Meshtastic Console by IK5XMK</title>

<link rel="stylesheet"
href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">

<style>

body{
background:#0d0d0d;
font-family:system-ui;
margin:0;
color:#eee;
}

.container{
max-width:750px;
margin:auto;
padding:20px;
}

h2{
text-align:center;
margin-bottom:20px;
font-weight:600;
}

.card{
background:#1a1a1a;
padding:20px;
border-radius:14px;
box-shadow:0 5px 20px rgba(0,0,0,0.5);
}

textarea{
width:100%;
height:90px;
font-size:16px;
padding:12px;
border-radius:10px;
border:1px solid #ccc;
background:white;
color:#222;
box-sizing:border-box;
resize:none;
}

.buttons{
margin-top:15px;
display:flex;
gap:12px;
flex-wrap:wrap;
}

button{
flex:1;
padding:14px;
font-size:16px;
border:none;
border-radius:10px;
cursor:pointer;
display:flex;
align-items:center;
justify-content:center;
gap:8px;
transition:0.2s;
font-weight:500;
}

.send{
background:#2ecc71;
color:white;
}

.send:hover{
background:#27ae60;
}

.node{
background:#3498db;
color:white;
}

.node:hover{
background:#2980b9;
}

.table-wrap{
margin-top:20px;
background:#1a1a1a;
border-radius:14px;
overflow:hidden;
box-shadow:0 5px 20px rgba(0,0,0,0.4);
}

table{
width:100%;
border-collapse:collapse;
font-size:14px;
}

thead{
background:#252525;
}

th{
padding:12px;
text-align:left;
font-weight:600;
font-size:13px;
color:#aaa;
}

td{
padding:10px;
border-top:1px solid #333;
}

tr:nth-child(even){
background:#161616;
}

tr:hover{
background:#222;
}

.nodebadge{
padding:3px 8px;
border-radius:6px;
font-weight:600;
font-size:13px;
color:white;
display:inline-block;
}

.time{
color:#aaa;
font-family:monospace;
}

.msg{
color:#ddd;
}

/* NOTIFICA */

#toast{
position:fixed;
top:20px;
left:50%;
transform:translateX(-50%) translateY(-100px);
background:#2ecc71;
color:white;
padding:14px 22px;
border-radius:12px;
font-size:15px;
box-shadow:0 10px 30px rgba(0,0,0,0.4);
display:flex;
align-items:center;
gap:10px;
transition:all .4s ease;
opacity:0;
z-index:1000;
}

#toast.show{
transform:translateX(-50%) translateY(0);
opacity:1;
}

</style>

</head>

<body>

<div class="container">

<h2><i class="fa-solid fa-radio"></i> Meshtastic Console</h2>

<div class="card">

<form method="post">

<textarea name="message" placeholder="Scrivi messaggio radio..."></textarea>

<div class="buttons">

<button class="send" type="submit" name="send_message">
<i class="fa-solid fa-paper-plane"></i>
Invia Messaggio
</button>

<button class="node" type="submit" name="send_nodeinfo">
<i class="fa-solid fa-satellite-dish"></i>
Invia Node Info
</button>

</div>

</form>

</div>

<div class="table-wrap">

<table id="msgtable">

<thead>
<tr>
<th width="70">Ora</th>
<th width="160">Nodo</th>
<th>Messaggio</th>
</tr>
</thead>

<tbody></tbody>

</table>

</div>

</div>

<div id="toast"></div>

<script>

const toastMessage = "<?php echo $toast_message; ?>";

function showToast(msg){

let toast=document.getElementById("toast");

toast.innerHTML='<i class="fa-solid fa-circle-check"></i>'+msg;

toast.classList.add("show");

setTimeout(()=>{

toast.classList.remove("show");

},3000);

}

window.onload=function(){

if(toastMessage!=""){
showToast(toastMessage);
}

const WS_SERVER="ws://"+window.location.hostname+":8765";

let ws;

function nodeColor(name){

let colors=[
"#e74c3c",
"#3498db",
"#9b59b6",
"#1abc9c",
"#e67e22",
"#f1c40f",
"#2ecc71"
];

let hash=0;

for(let i=0;i<name.length;i++){
hash=name.charCodeAt(i)+((hash<<5)-hash);
}

return colors[Math.abs(hash)%colors.length];

}

function connectWS(){

ws=new WebSocket(WS_SERVER);

ws.onopen=function(){
console.log("WebSocket connesso");
};

ws.onclose=function(){
setTimeout(connectWS,3000);
};

ws.onmessage=function(event){

let data=JSON.parse(event.data);

let tbody=document.querySelector("#msgtable tbody");

let row=tbody.insertRow(0);

let c1=row.insertCell(0);
let c2=row.insertCell(1);
let c3=row.insertCell(2);

c1.innerHTML='<span class="time">'+data.time+'</span>';

let color=nodeColor(data.node);

c2.innerHTML='<span class="nodebadge" style="background:'+color+'">'+data.node+'</span>';

c3.innerHTML='<span class="msg">'+data.text+'</span>';

if(tbody.rows.length>60){
tbody.deleteRow(60);
}

};

}

connectWS();

};

</script>

</body>
</html>
