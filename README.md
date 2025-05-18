
# Projects
Repository for coding projects. Other repositories may be moved to here in the future.


# PicarX
_I am using the Sunfounder PicarX with a Rasberry Pi 5._

The Mahler file is not in this repository, but is a recording of Pierre Boulez conducting Mahler Symphony No. 6.

The purpose of this is to interact with the PicarX.

I have found it is pretty good at chess, but starts forgetting position in the middlegame.

##DOES NOT WORK - FOR NOW

# Decoder

##DOES WORK

Give it an alphabet substitution or ceaser cipher and it will figure it out. Preferably 200+ char. Try not to use names or urls, as that trips it up for now.

EXAMPLE:
python3 auto_sub_solver.py --clean "Yjr wiovl ntpem gpc kiqad pbrt yjr zsxu fph. O zolr wiovl gpcrd. Yjru str brtu dzu smf dqsty. O jpar yjr fph fprd mpy hry qsf. Xrntsd szdp rmkpu zrsaomh smf kiqaomh. Yjru jsbr rurd pm yjr dofr pg yjrot jrsf yp dapy atrfsyptd. Sm rcyts snozoyu pg dmslrd od yp drr jrsy. yjod szzped yjrq yp dapy zogr rsdozu."
[*] Auto params  restarts=102  iterations=9180

[+] Best key  : PVXSWDFGUHJKNBIOMEARYCQZTL
[+] Sense‑ratio: 93.22%

===== Decryption =====

THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG. I LIKE QUICK FOXES. THEY ARE VERY SLY AND SMART. I HOPE THE DOG DOES NOT GET MAD. ZEBRAS ALSO ENJOY LEAPING AND JUMPING. THEY HAVE EYES ON THE SIDE OF THEIR HEAD TO SPOT PREDATORS. AN EXTRA ABILITY OF SNAKES IS TO SEE HEAT. THIS ALLOWS THEM TO SPOT LIFE EASILY.
ezra@Ezras-Air Decode % python3 auto_sub_solver.py --clean "Yjr wiovl ntpem gpc kiqad pbrt yjr zsxu fph. O zolr wiovl gpcrd. Yjru str brtu dzu smf dqsty. O jpar yjr fph fprd mpy hry qsf. Xrntsd szdp rmkpu zrsaomh smf kiqaomh. Yjru jsbr rurd pm yjr dofr pg yjrot jrsf yp dapy atrfsyptd. Sm rcyts snozoyu pg dmslrd od yp drr jrsy. yjod szzped yjrq yp dapy zogr rsdozu."
[*] Auto params  restarts=102  iterations=9180

[+] Best key  : PVXSWDFGUHJKNBIOMEARYCQZTL
[+] Sense‑ratio: 93.44%

===== Decryption =====

THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG. I LIKE QUICK FOXES. THEY ARE VERY SLY AND SMART. I HOPE THE DOG DOES NOT GET MAD. ZEBRAS ALSO ENJOY LEAPING AND JUMPING. THEY HAVE EYES ON THE SIDE OF THEIR HEAD TO SPOT PREDATORS. AN EXTRA ABILITY OF SNAKES IS TO SEE HEAT. THIS ALLOWS THEM TO SPOT LIFE EASILY.


__NOTE__
_Please do not use chars !, ', or " due to bash problems._

### HOW TO USE:

*You might use python instead of python3.*
1. python3 auto_sub_solver.py; This can be used for quick, simple encoded messages.
2. python3 auto_sub_solver.py --clean; This is generally better and helps accuracy.
3. python3 auto_sub_solver.py --clean -r RESTARTS -i ITERATIONS. This helps fine tune; Generally longer texts need less restarts and iterations.
4. python3 auto_sub_solver.py --clean -r RESTARTS -i ITERATIONS --file file.txt; This can be used for long files, like when I decoded the US constitution. You edit file.txt first.
