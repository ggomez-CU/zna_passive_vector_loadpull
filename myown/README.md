  This is a repository for the MMIC test results and code for the testing done by Grace Gomez of her own MMICs over the summer of 2025

# Hardware Set-up and Calibration procedure 

This will be documented when I have time to organize my hectic note taking. eta Sept. 2025

# Installation

To for do this:

Idk ask grant or Google

# TODO

### Technical detail: Category system and Drivers

- literally everything.

### Start virtual environment ###

For repo testing, a virtual enviorment was set up. This means all  required libraries can be found in... I am pretty sure there is a file

```
python -m venv venv
```

Activate for windows:

```
. venv\Scripts\activate
```

Activate for Mac:

```
. venv/bin/activate
```

# Operating Procedure #
Make sure system is cal'd both power and sparam (s first) and RF is off and driver is on. Double check connections. 


# Required packages #

```
pip install -r requirements.txt -y
```

# Set up PNA
Stimulus: power off (while initializing)
Freq: 10 GHz
Freq offset: on
Sweep:Number of points: 1
channel: hardware: test set up: external ref
set receiver atten to 20dB
power: -27 on