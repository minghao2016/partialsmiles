import sys
from elements import elements
import valence

bondchars = "-=#$\\/"
bondorders = [1, 2, 3, 4, 1, 1]
CLOSE, OPEN = range(2)

aromatic_list = ["c", "n", "p", "o", "s", "te", "se", "b"] # more?
aromatic_set = set(aromatic_list)
firstLetterOfElements = set(x[0] for x in list(elements.keys()) + aromatic_list)

def ToBondOrder(bondchar):
    idx = bondchars.index(bondchar)
    return bondorders[idx] # returns 1 for empty string

class Bond:
    def __init__(self, beg, end, bo):
        self.beg = beg
        self.end = end
        self.bo = bo
        self.arom = False
        self.idx = -1
    def getNbr(self, atom):
        return self.beg if self.end==atom else self.end

class Atom:
    def __init__(self, element, charge=0):
        self.element = element
        self.charge = charge
        self.implh = -1
        self.arom = False
        self.idx = -1
        self.bonds = []
        self.isotope = 0
    def __repr__(self):
        return "Atom(elem=%d,chg=%d)" % (self.element, self.charge)
    def getExplicitDegree(self):
        return len(self.bonds)
    def getExplicitValence(self):
        return sum(bond.bo for bond in self.bonds)

class Molecule:
    def __init__(self):
        self.atoms = []
        self.bonds = []
    def addAtom(self, symbol, prev, bondchar):
        element = ToElement(symbol)
        atom = Atom(element)
        atom.arom = symbol[0].islower()
        atom.idx = len(self.atoms)
        self.atoms.append(atom)
        if prev is not None:
            bo = ToBondOrder(bondchar)
            bond = self.addBond(prev, atom, bo)
            if atom.arom and prev.arom and not bondchar:
                bond.arom = True
        return atom
    def addBond(self, beg, end, bo):
        bond = Bond(beg, end, bo)
        bond.idx = len(self.bonds)
        self.bonds.append(bond)
        beg.bonds.append(bond)
        end.bonds.append(bond)
        return bond
    def getBond(self, atomA, atomB):
        for nbr_bond in atomA.bonds:
            nbr = nbr_bond.end if nbr_bond.beg == atomA else nbr_bond.beg
            if nbr == atomB:
                return nbr_bond
        return None
    def debug(self):
        for i, atom in enumerate(self.atoms):
            print("Atom: %d %s charge %d implh %d expdeg %d iso %d arom %d" % (i, atom.element, atom.charge, atom.implh, atom.getExplicitDegree(), atom.isotope, atom.arom))
        for i, bond in enumerate(self.bonds):
            print("Bond: %d %d->%d bo %d arom %d" % (i, bond.beg.idx, bond.end.idx, bond.bo, bond.arom))
        for bcsymbol, (atomidx, bondchar) in self.openbonds.items():
            print("Open bond: %d->? bc '%s'" % (atomidx, bondchar))
    def __repr__(self):
        return "Molecule(atoms=%s)" % [str(x) for x in self.atoms]

def CreateError(text, smi, location):
    error = [text, "  " + smi, " "*(location+2)+"^"]
    return "\n".join(error)

class SmilesParser:
    def __init__(self, partial, rulesToIgnore):
        self.partial = partial
        self.rulesToIgnore = rulesToIgnore
    def parse(self, smi):
        self.smi = smi
        self.N = len(smi)
        self.mol = Molecule()
        self.openbonds = {} # dict from symbol -> (atom idx, bondchar)
        self.hcount = []
        self.idx = 0
        self.prev = [None]
        self.bondchar = None
        self.smiidx = []
        while self.idx < self.N:
            x = smi[self.idx]
            if x == '.':
                if not self.rulesToIgnore & 1 and (self.idx == 0 or smi[self.idx-1]=='.'):
                    self.handleError("Empty molecules are not allowed")
                if self.bondchar:
                    self.handleError("An atom must follow a bond symbol")
                self.prev[-1] = None
                self.handleError(self.validateSyntax(dot=True))
                self.idx += 1
            elif x == ')':
                if not self.rulesToIgnore & 2 and (self.idx > 1 and smi[self.idx-1]=='('):
                    self.handleError("Empty branches are not allowed")
                if self.bondchar:
                    self.handleError("An atom must follow a bond symbol")
                self.prev.pop()
                if not self.prev:
                    self.handleError("Unmatched close parenthesis")
                self.idx += 1
            elif x == '(':
                if not self.rulesToIgnore & 4 and (self.prev[-1] is None or smi[self.idx-1]=='('):
                    self.handleError("An atom must precede an open parenthesis")
                if self.bondchar:
                    self.handleError("A bond symbol should not precede an open parenthesis")
                self.prev.append(self.prev[-1])
                self.idx += 1
            elif x in bondchars:
                if self.prev[-1] is None:
                    self.handleError("An atom must precede a bond symbol")
                if self.bondchar:
                    self.handleError("Only a single bond symbol should be used")
                self.bondchar = x
                self.idx += 1
            elif x.isdigit() or x=='%':
                if self.prev[-1] is None:
                    self.handleError("An atom must precede a bond closure symbol")
                self.handleError(self.handleBCSymbol())
            elif x in "[*BCNPOSFIbcnpos":
                self.handleError(self.parseAtom())
            else:
                self.handleError("Illegal character")

        self.handleError(self.validateSyntax())
        self.handleError(self.validateValence())
        self.mol.openbonds = dict(self.openbonds)
        return self.mol

    def handleError(self, msg):
        if msg:
            if type(msg) == type(()):
                raise Exception(CreateError(msg[0], self.smi, msg[1]))
            else:
                raise Exception(CreateError(msg, self.smi, self.idx))

    def validateValence(self):
        # ----- Check for unusual valence -------
        self.setImplicitHydrogenCount()
        for atom in self.mol.atoms:
            if not self.hasCommonValence(atom):
                return ("Uncommon valence or charge state", self.smiidx[atom.idx])

    def validateSyntax(self, dot=False):
        # ----- Check syntax -------
        # Check that all ring bonds have been closed
        # Check that all brackets have been closed
        if self.partial:
            return None
        if (not dot or not self.rulesToIgnore & 16) and self.openbonds:
            text = "s have" if len(self.openbonds) > 1 else " has"
            return "{} ring opening{} not been closed".format(len(self.openbonds), text)
        if not self.rulesToIgnore & 8 and len(self.prev) > 1:
            text = "branches have" if len(self.prev) > 2 else "branch has"
            return "{} {} not been closed".format(len(self.prev)-1, text)
        return None

    def setImplicitHydrogenCount(self):
        for i, atom in enumerate(self.mol.atoms):
            hcount = self.hcount[i]
            if hcount > -1:
                atom.implh = hcount
            else:
                explicitvalence = atom.getExplicitValence()
                implicitvalence = SmilesValence(atom.element, explicitvalence)
                implh = implicitvalence - explicitvalence
                if implh > 0 and atom.arom:
                    implh -= 1
                atom.implh = implh

    def handleBCSymbol(self):
        x = self.smi[self.idx]
        if x == "%":
            bcsymbol = self.smi[self.idx:self.idx+3]
            self.idx += 2
        else:
            bcsymbol = x
        if bcsymbol in self.openbonds:
            opening, openbc = self.openbonds.pop(bcsymbol)
            if opening == self.prev[-1]:
                return "Cannot have a bond opening and closing on the same atom"
            if self.mol.getBond(opening, self.prev[-1]):
                return "Cannot have a second bond between the same atoms"
            openbo = 0 if not openbc else ToBondOrder(openbc)
            closebo = 0 if not self.bondchar else ToBondOrder(self.bondchar)
            if closebo and openbo and closebo != openbo:
                return "Inconsistent bond orders"
            bo = closebo if closebo else openbo
            arom = False
            if not bo:
                if opening.arom and self.prev[-1].arom:
                    arom = True
                bo = 1
            bond = self.mol.addBond(opening, self.prev[-1], bo)
            bond.arom = arom
        else:
            self.openbonds[bcsymbol] = (self.prev[-1], self.bondchar)
        self.idx += 1
        self.bondchar = None
        return None

    def getAdjustedExplicitValence(self, atom):
        """Adjust the explicit valence for the attachee in partial SMILES
        
        For example: "C(" has explicit valence of 0, but adjusted to 1
        For example: "C=" has explicit valence of 0, but adjusted to 2
        "C" -> 0, whether or not dots are allowed
        "C(" -> 1 (either way)
        
        """
        ans = atom.getExplicitValence()
        if not self.partial or atom != self.prev[-1]:
            return ans
        if self.bondchar:
            ans += ToBondOrder(self.bondchar)
        elif self.smi[-1] in "([":
            ans += 1
        for bcsymbol, (beg, symbol) in self.openbonds.items():
            if beg == atom:
                ans += 1 if not symbol else ToBondOrder(symbol)
                break
        return ans

    def hasCommonValence(self, atom):
        data = valence.common_valencies.get(atom.element, None) 
        # How to handle elements not in the list?
        if data is None:
            return False # Alternatively, you may wish to return True
        allowed = data.get(atom.charge, None)
        if allowed is None:
            return False # unusual charge state
        explval = atom.getExplicitValence()
        if valence.NeedsDblBond(atom): # adjust valence for aromatic atoms
            explval += 1
        totalvalence = explval + atom.implh
        if totalvalence in allowed:
            return True
        # Nitrogen can only have 3 bonds (even if hypervalent)
        if atom.element==7 and atom.getExplicitDegree() + atom.implh > 3:
            return False
        if self.partial:
            if totalvalence <= max(allowed):
                return True # still possibly normal valence
        # Note to reader: you could comment out the following line if
        # you don't need to support TEMPO-like (stable) oxygen radicals
        if atom.element==8 and atom.charge==0 and explval==1 and atom.implh==0 and valence.IsAttachedToNitrogen(atom): # TEMPO-like
            return True
        return False


    def notAtEnd(self):
        return self.idx < self.N

    def atEnd(self):
        return self.idx == self.N

    def incrementAndTestForEnd(self):
        self.idx += 1
        if self.atEnd():
            if self.partial:
                return True, None
            else:
                return True, "An open square brackets is present without the corresponding close square brackets"
        return False, None

    def parseAtom(self):
        x = self.smi[self.idx]

        if x == '[':
            end, msg = self.incrementAndTestForEnd()
            if end:
                return msg

            # Handle isotope
            if self.smi[self.idx].isdigit():
                isotope = int(self.smi[self.idx])
                if isotope == 0:
                    return "Isotope value of 0 not allowed"
                end, msg = self.incrementAndTestForEnd()
                if end:
                    return msg
                if self.smi[self.idx].isdigit():
                    isotope = isotope*10 + int(self.smi[self.idx])
                    end, msg = self.incrementAndTestForEnd()
                    if end:
                        return msg
                    if self.smi[self.idx].isdigit():
                        isotope = isotope*10 + int(self.smi[self.idx])
                        end, msg = self.incrementAndTestForEnd()
                        if end:
                            return msg
            else:
                isotope = 0

            # Handle element
            if self.smi[self.idx] not in firstLetterOfElements:
                return "An element symbol is required"
            if self.idx+1 < self.N and self.smi[self.idx].upper() + self.smi[self.idx+1] in elements:
                symbol = self.smi[self.idx:self.idx+2]
                self.idx += 1
            else:
                symbol = self.smi[self.idx]
            end, msg = self.incrementAndTestForEnd()
            if end:
                return msg
            
            # Handle tet stereo
            if self.smi[self.idx] == '@':
                end, msg = self.incrementAndTestForEnd()
                if end:
                    return msg
                if self.smi[self.idx] == '@':
                    end, msg = self.incrementAndTestForEnd()
                    if end:
                        return msg

            # Handle H count
            if self.smi[self.idx] == 'H':
                end, msg = self.incrementAndTestForEnd()
                if end:
                    return msg
                if self.smi[self.idx].isdigit():
                    hcount = int(self.smi[self.idx])
                    end, msg = self.incrementAndTestForEnd()
                    if end:
                        return msg
                else:
                    hcount = 1
            else:
                hcount = 0

            # Handle charge
            if self.smi[self.idx] in "+-":
                charge = 1 if self.smi[self.idx] == '+' else -1
                end, msg = self.incrementAndTestForEnd()
                if end:
                    return msg
                if self.smi[self.idx].isdigit():
                    numcharge = int(self.smi[self.idx])
                    charge *= numcharge
                    end, msg = self.incrementAndTestForEnd()
                    if end:
                        return msg
                elif self.smi[self.idx] in "+-":
                    numcharge = 1
                    while self.smi[self.idx] == self.smi[self.idx-1]:
                        numcharge += 1
                        end, msg = self.incrementAndTestForEnd()
                        if end:
                            return msg
                    charge *= numcharge
            else:
                charge = 0

            # Handle close-bracket
            if self.smi[self.idx] == ']':
                self.idx += 1
            else:
                return "Missing the close bracket"

        elif self.notAtEnd() and self.smi[self.idx:self.idx+2] in ["Cl", "Br"]:
            symbol = self.smi[self.idx:self.idx+2]
            self.idx += 2
            hcount = -1
            charge = 0
            isotope = 0
        else:
            self.idx += 1
            symbol = x
            hcount = -1
            charge = 0
            isotope = 0

        atom = self.mol.addAtom(symbol, self.prev[-1], self.bondchar if self.bondchar else "")
        atom.charge = charge
        atom.isotope = isotope
        self.prev[-1] = atom
        self.hcount.append(hcount)
        self.smiidx.append(self.idx-1)

        # Reset
        self.bondchar = None

valencemodel = {
        5: [3], 6: [4], 7: [3, 5], 15: [3, 5],
        8: [2], 16: [2, 4, 6],
        9: [1], 17: [1], 35: [1], 53: [1]
        }
def SmilesValence(elem, val):
    implvalences = valencemodel[elem]
    for implvalence in implvalences:
        if val <= implvalence:
            return implvalence
    return val

def ToElement(symbol):
    if symbol[0].islower():
        symbol = symbol[0].upper() + symbol[1:]
    return elements[symbol]

def ParseSmiles(smi, partial, rulesToIgnore=0):
    sp = SmilesParser(partial, rulesToIgnore);
    mol = sp.parse(smi)
    return mol

def main():
    text = sys.argv[1]
    mol = ParseSmiles(text, False)
    mol.debug()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
