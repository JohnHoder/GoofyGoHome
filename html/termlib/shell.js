// *** request sample ***
// mass:werk, N.Landsteiner 2007

var term;

var help = [
	'%+r -~== GoofyGoHome Shell ==~- %-r',
	' '
];

function termOpen() {
	if ((!term) || (term.closed)) {
		term = new Terminal(
			{
				x: -50,
				y: -30,
				cols: 138,
				rows: 24,
				termDiv: 'termDiv',
				bgColor: '#232e45',
				greeting: help.join('\n'),
				handler: termHandler,
				exitHandler: termExitHandler
			}
		);
		term.open();
		
		// dimm UI text
		var mainPane = (document.getElementById)?
			document.getElementById('mainPane') : document.all.mainPane;
		if (mainPane) mainPane.className = 'lh15 dimmed';
	}
}

function termExitHandler() {
	// reset the UI
	var mainPane = (document.getElementById)?
		document.getElementById('mainPane') : document.all.mainPane;
	if (mainPane) mainPane.className = 'lh15';
}

function pasteCommand(text) {
	// insert given text into the command line and execute
	var termRef = TermGlobals.activeTerm;
	if ((!termRef) || (termRef.closed)) {
		alert('Please open the terminal first.');
		return;
	}
	if ((TermGlobals.keylock) || (termRef.lock)) return;
	termRef.cursorOff();
	termRef._clearLine();
	for (var i=0; i<text.length; i++) {
		TermGlobals.keyHandler({which: text.charCodeAt(i), _remapped:true});
	}
	TermGlobals.keyHandler({which: termKey.CR, _remapped:true});
}

function termHandler() {
	this.newLine();
	
	this.lineBuffer = this.lineBuffer.replace(/^\s+/, '');
	var argv = this.lineBuffer.split(/\s+/);

	this.send
	(
		{
			url: "/proc?cmd=" + this.lineBuffer,
			method: 'get',
			callback: myServerCallback
		}
	);
	this.prompt();
}

function myServerCallback() {
	var response=this.socket;
	//this.write(response.responseText);
	if (response.success) {
		this.write('\n' + response.responseText);
		// temp = response.responseText;
		// const lines = ((temp).match(/\r?\n/g)).length + 1;
		// if (lines > 1){
		// 	this.write('\n' + response.responseText);
		// }
		// else{
		// 	this.write(response.responseText);
		// }
	}
	else {
		var s='Request failed: ' + response.status + ' ' + response.statusText;
		if (response.errno) s +=  '\n' + response.errstring;
		this.write(s);
	}
	this.prompt();
}
