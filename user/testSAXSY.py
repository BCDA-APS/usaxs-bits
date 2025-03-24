"""
BS plan to run finite test on saxsy satge.

load this way:

     %run -im user.testTSAXSY
     
     then RE(testSAXSY())
"""    
    
     
from bluesky import plan_stubs as bps

from instrument.devices.stages import a_stage, d_stage, saxs_stage  
    

def testSAXSY():    
    
	i = 0
	while i < 200: 
		i+=1
		print(f"Iteration ={i}")
		yield from bps.mv(saxs_stage.y, -270)
		yield from bps.sleep(3)  	# delay 5 sec
		yield from bps.mv(saxs_stage.y, -15)    
		yield from bps.sleep(10)  	# delay 20 sec



