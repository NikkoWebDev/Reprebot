var winRef = null;
function oW(targetURL,ancho,alto,name)
{
 var opciones = "toolbar=yes,location=no,directories=no,status=yes,menubar=yes,scrollbars=yes,resizable=yes,width="+ancho+",height="+alto;
 if (  winRef != null  ) winRef.close();
 try {
	 winRef = window.open(targetURL,name,opciones);
	 winRef.focus(); 
 }
 catch(err) {
	 txt="There was an error on this page.\n\n";
	  txt+="Error description: " + err.description + "\n\n";
	  txt+="Click OK to continue.\n\n";
	  alert(txt);
 }

}
