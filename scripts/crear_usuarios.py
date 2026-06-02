"""Crea cuentas Firebase Auth para los participantes de la tesis.

Uso:
    cd D:\Backend
    python scripts/crear_usuarios.py

Por cada entrada de USUARIOS:
  - Crea un usuario en Firebase Auth con el email y la contraseña por defecto.
  - Si el usuario ya existe, lo reutiliza (idempotente).
  - Crea/actualiza el documento en Firestore con riotIdVinculado.

Contraseña por defecto: GameWell2024!
  -> Los participantes deben cambiarla al primer inicio de sesión.
  -> Puedes modificar DEFAULT_PASSWORD antes de ejecutar.
"""
import sys
from pathlib import Path

# Permite importar desde el paquete app/ (clave firebase-key.json)
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import datetime, timezone

# ─── Configuración ────────────────────────────────────────────────────
KEY_PATH      = BASE / "firebase-key.json"
DEFAULT_PASSWORD = "GameWell2024!"

# ─── Mapeo email -> Riot ID (en orden del dataset) ─────────────────────
USUARIOS = [
    ("itzel.rr2003@gmail.com",               "Aiso#P2W"),
    ("santillanescudero10@gmail.com",        "Tyson#nlove"),
    ("marioromero200201@gmail.com",          "TLK320#LAS"),
    ("axeljhosmell13@gmail.com",             "franchoski17#LAS"),
    ("ebaldovinom95@gmail.com",              "KESMAN#LAS"),
    ("josueflorian2004@gmail.com",           "Rey Oscuro#Leon"),
    ("sdiegofabrizio@gmail.com",             "Jon Blackfyre#LAS"),
    ("carlosalcedojavier@gmail.com",         "Ritchan#LAS"),
    ("loladare.44@gmail.com",                "SaiC#RBC"),
    ("jhomi.free@gmail.com",                 "Baruff44#XII"),
    ("dr1778614@gmail.com",                  "Näle#LAS"),
    ("cabah5720@gmail.com",                  "smurf1505#smurf"),
    ("francowoken13@gmail.com",              "Kîƒµńø#LAS"),
    ("holguin98fx@gmail.com",               "VieguitoMaragona#URF"),
    ("rodrigoburga40@gmail.com",             "anwnie#LAS"),
    ("rodriflaco930@gmail.com",              "Michsss#6945"),
    ("ivanakatrinaramos@gmail.com",          "gato perkin#LAS"),
    ("anthonyhancco.0708@gmail.com",         "CorneliaMolina#AMPAY"),
    ("jennifer15aries@gmail.com",            "Langosta Cosmica#fran"),
    ("pablocortez1507@gmail.com",            "Knasky#Jaz"),
    ("moleve27@gmail.com",                   "PinpónEsUnMuñeco#WA0S"),
    ("samu204022@gmail.com",                 "Roruwu#42069"),
    ("fernandoalabanuch@gmail.com",          "Rin Matsuoka#FREE"),
    ("charlesfred.jgb@gmail.com",            "Zombie Slayer#LAS"),
    ("marlene97vm@gmail.com",                "Veronsqui#UNDs"),
    ("ashmitaggarwal2008@gmail.com",         "VengadorM#LAS"),
    ("bazanbetsy345@gmail.com",              "saroo13#LAS"),
    ("jeescuderos@ucvvirtual.edu.pe",        "TeZ#Deus"),
    ("krnobre11@gmail.com",                  "TacitaConTecito#LAS"),
    ("ritaaa.spm@gmail.com",                 "tandoe#LAS"),
    ("csangellina@gmail.com",               "Morjelakus#zaz"),
    ("dishapatel.nmims@gmail.com",           "Severity#666"),
    ("andervillaorduna@gmail.com",           "Moon#cito"),
    ("kcamposva@ucvvirtual.edu.pe",         "Maaæ#LAS1"),
    ("dianalinares2000.dvlz@gmail.com",      "RubiaFashion#LAS"),
    ("steffescudero07@gmail.com",            "MOONQUI#LAS"),
    ("alvaro.gensollen.suarez@gmail.com",    "Toky#Wena"),
    ("sotoprincipekaty05@gmail.com",         "tio goldo#1984"),
    ("ginrockaz@gmail.com",                  "Colan#LAS"),
    ("maximoenriquelavadopajuelo@gmail.com", "GotGaren#1997"),
    ("kiarabts56@gmail.com",                 "Cubito#4444"),
    ("xiomarasaldana326@gmail.com",          "DPontiacBandit#LAS"),
    ("luzpatricio05@gmail.com",              "agutin#LLL"),
    ("danielazbxd@gmail.com",               "the adc is#UwU"),
    ("jime.hernandez.f@gmail.com",           "TilinDijoElBardo#LAS"),
    ("aaronlopezsevillano2018@gmail.com",    "Felpa16#LAS"),
    ("vtarazonasanchez@gmail.com",           "Chinche Poroto#999"),
    ("nicolaxtao@gmail.com",                 "TeemoLicion#002"),
    ("andrealop861@gmail.com",               "NoxFler#LAS"),
    ("jaironilo18@gmail.com",                "Princesa Support#3505"),
    ("malosammakatbf@gmail.com",             "Weyes Blood#0519"),
    ("david.dahhhhh@gmail.com",              "katseye enjoyerr#T1LAS"),
    ("alex6200.sk8@gmail.com",               "Vaundy#3671"),
    ("royervalentinaraucogutarra@gmail.com", "Â Û R Ë Ł Ï Ã H#LAS"),
    ("joaquincalderonsa@gmail.com",          "Aress 2431#NDS"),
    ("aron18vidal@gmail.com",                "CrimenMusical#LAS"),
    ("suymmybernardo@gmail.com",             "Gla#LAS"),
    ("adbah0818@gmail.com",                  "kilefaa#LAS"),
    ("charlenyrg@gmail.com",                "Affection#1111"),
    ("stephenwilliamh17@gmail.com",          "Dvd#2799"),
    ("grgromit1233@gmail.com",               "Michael Olise#6x7vn"),
    ("abduels2005@gmail.com",                "INSECTOS#MVP"),
    ("paulo2005torrejon@gmail.com",          "Lucas#Abs"),
    ("edwintorresperales@gmail.com",         "Todoko#LAS"),
    ("max.smhit@gmail.com",                  "Ranser#434"),
    ("jneminz24@gmail.com",                  "LoKio#LAS"),
    ("zentoo31@gmail.com",                   "Chosar#SPQR"),
    ("santillanae@gmail.com",                "Nagi#2880"),
    ("carlosmendoza@gmail.com",              "YusiGuma#LAS"),
    ("ana.lopez84@gmail.com",                "Webo#LAS"),
    ("josef123@gmail.com",                   "ferkk#111"),
    ("mariagonzalezx@gmail.com",             "rer#16180"),
    ("luis_fernandez77@gmail.com",           "Kuro#IRON"),
    ("sofiarojas@gmail.com",                 "OddsAgainstMe#1905"),
    ("diego.torresk9@gmail.com",             "Doron#Elle"),
    ("camilavargas21@gmail.com",             "La magia del sur#4444"),
    ("juanperezzx@gmail.com",                "Luuuu#max"),
    ("valentina.mq@gmail.com",               "0FF THE GRID#LAS"),
    ("alejandrorojas@gmail.com",             "kaybroak#MVP"),
    ("karla.mendoza58@gmail.com",            "KasFesp#LAS"),
    ("miguelx7@gmail.com",                   "Salteño Promedio#ups"),
    ("danielaperalez@gmail.com",             "zzz#trap"),
    ("fernandocv91@gmail.com",               "God ryze#LAS"),
    ("lucia.torresq@gmail.com",              "Ðiush#White"),
    ("milagr0srm@gmail.com",                 "LoanniZz#DEUS"),
    ("adriangmez@gmail.com",                 "TTV Pikabam#001"),
    ("ximenaf82@gmail.com",                  "AvHPeaceMaker#LAS"),
    ("estebancruzx@gmail.com",               "PeelMe#Tom"),
    ("natalimora17@gmail.com",               "Pmx#LAS"),
    ("kevinramos55@gmail.com",               "El Garbanzo#LAS"),
    ("ricardopm@gmail.com",                  "Duki#7763"),
    ("oscar.mzq@gmail.com",                  "fedejuega#LAS"),
    ("manuelcr7@gmail.com",                  "iJoker#LAS"),
    ("renatoqm@gmail.com",                   "jzsoe#LAS"),
    ("sebastianramos@gmail.com",             "Haewon#1998"),
    ("karen94v@gmail.com",                   "T1Nyuloi#Nashe"),
    ("jhonatanlopez@gmail.com",              "iPloxSB#1476"),
    ("milagrosx21@gmail.com",                "Willimerca#6666"),
    ("adriansotoq@gmail.com",                "TotooR2#LAS"),
    ("carlosviaje@gmail.com",                "JacquesLacan#1230"),
    ("mariasolventa@gmail.com",              "RJAV#1998"),
    ("juanmercado@gmail.com",                "Nestornadoxs#LAS"),
    ("lauracoc@gmail.com",                   "Reish99#2001"),
    ("danielvt@gmail.com",                   "MadLife#NCS"),
    ("alejandraponce@gmail.com",             "LoGoZ#LAS"),
    ("fabianacuna@gmail.com",                "SkeeLetor#LAS"),
    ("marianafloresv@gmail.com",             "Gekidou#512"),
    ("estebanmorales55@gmail.com",           "regicida#LAS69"),
    ("franciscoramos64@gmail.com",           "Bling Bling#lowie"),
    ("sebastianvargss9@gmail.com",           "Asa Mitaka#Kelly"),
    ("santiagojm@gmail.com",                 "Thom Merrilin#LAS"),
    ("ramirezsj@gmail.com",                  "Thaizor#LAS"),
    ("fernandezlu@gmail.com",                "Pingu#SEES"),
    ("carlosrt23@gmail.com",                 "SinverGWENza#Gwen"),
    ("gabrielhf89@gmail.com",                "222369#222"),
    ("castrovm_04@gmail.com",                "Mewi#LAS"),
    ("salazarma@gmail.com",                  "moko#1040"),
    ("sebasobree22@gmail.com",               "Barry Chopper#LAS"),
    ("fer07979@gmail.com",                   "Matisinho#000"),
    ("maytesv1@gmail.com",                   "Amal2#LAS"),
    ("huamanlg08@gmail.com",                 "Dsá#Meins"),
    ("rivermc71@gmail.com",                  "Takirø#弓の神7R"),
    ("delgadoore@gmail.com",                 "Teemomazos#PER"),
    ("quispebm1433@gmail.com",               "LoboAlfaKevin#LAS"),
    ("carranzafl19@gmail.com",               "TeShacølaCtM#LAS"),
    ("rosalesmn2660@gmail.com",              "Pirlo#ush"),
    ("castromf70@gmail.com",                 "Dito#rey"),
    ("ashleytn82@gmail.com",                 "ignaa42#LAS"),
    ("castillomg680zz@gmail.com",            "Mvko#LAS"),
    ("jereforeve2@gmail.com",                "el prokilll#LAS"),
    ("ashleymv0009@gmail.com",               "kenyu3#LAS"),
    ("gianfranqtt@gmail.com",                "jalamee#LAS"),
    ("alondraxx202@gmail.com",               "Muerto#666"),
    ("alessandretii.i@gmail.com",            "ySan97#f22b2"),
    ("janahilaryx.vela@gmail.com",           "SOUL#JPN"),
    ("ivanoskia@gmail.com",                  "Joa#GLHF"),
    ("digoherrsan@gmail.com",                "Sunmy#LAS"),
    ("crisstiancastroca@gmail.com",          "Felo#BEAR"),
    ("zoesinas.81@gmail.com",                "77pablito#CAI"),
    ("romerosoriamayeline@gmail.com",        "RP Glasman2#LAS"),
    ("juanperez21@gmail.com",                "El Rey Henry#KING"),
    ("m.lopez2002@gmail.com",                "ATC PØLPHOENIX#LAS1"),
    ("carlos_ramirez98@gmail.com",           "Whiskas#Curru"),
    ("anagarcia17@gmail.com",                "Oticangi#PPP"),
    ("ltorresx23@gmail.com",                 "RIP in peperonni#LAS"),
    ("sofi.mendz@gmail.com",                 "ZT4#LAS"),
    ("diegof20@gmail.com",                   "sanzok#LAS"),
    ("cvargas2001@gmail.com",                "IlachOne#6381"),
    ("joserojas89@gmail.com",                "Levhen#LAS"),
    ("vale_cast22@gmail.com",                "Saidpalao#AMPAY"),
    ("kevh_03@gmail.com",                    "ajinomen#9038"),
    ("andreasilva99@gmail.com",              "Lordans#6969"),
    ("miguelm.2000@gmail.com",               "LIT KILLAH#412"),
    ("paolaortiz7@gmail.com",                "vamosadecirquesi#LAS"),
    ("alexgzz21@gmail.com",                  "JT 01#LAS"),
    ("dani_san03@gmail.com",                 "ComidaDelFuturo氣#ATEN"),
    ("ricfdez20@gmail.com",                  "Giann#LATAM"),
    ("lucian99@gmail.com",                   "Vyak#LAS"),
    ("adrimtz17@gmail.com",                  "xHoneyFish#CHL"),
    ("ferruizx@gmail.com",                   "Jarthar#LAS"),
    ("javmendoza21@gmail.com",               "Vayne player 1#LAS"),
    ("karlar98@gmail.com",                   "darling#zzz"),
    ("sebaparedes@gmail.com",                "LKING#MH1"),
    ("xim.cab23@gmail.com",                  "SuruyoDelSodimac#LAS"),
    ("angelosalv98@gmail.com",               "SebastianMR#2404"),
    ("meliq_22@gmail.com",                   "daegu#LAS"),
    ("franco.v20@gmail.com",                 "Intss#LAS"),
    ("dianapn01@gmail.com",                  "BlackModerm10#0000"),
    ("brayanchv17@gmail.com",                "S1m0n#2277"),
    ("ren.ag98@gmail.com",                   "Shamta#LAS"),
    ("crisesp03@gmail.com",                  "Dr Tommy#Crybb"),
    ("fio.reyes20@gmail.com",                "Nav#210"),
    ("maurimed@gmail.com",                   "TheBoss#T3tas"),
    ("gabycast98@gmail.com",                 "selfless#pain"),
    ("pieros22@gmail.com",                   "SOS RE WACHINN#LAS"),
    ("nicmol01@gmail.com",                   "Kab#DUHR"),
    ("jeanrv03@gmail.com",                   "Labubu#1251"),
    ("luci_vega20@gmail.com",                "Hustlee Hard 304#304"),
    ("edgcar23@gmail.com",                   "BABOSA#lmao"),
    ("maricard20@gmail.com",                 "NoWitness#CBA"),
    ("raulg99@gmail.com",                    "taitun#LAS"),
    ("ale.mir21@gmail.com",                  "Creeping Derp#LAS"),
    ("oscdel02@gmail.com",                   "jordi el tulachi#LAS"),
    ("noemndz03@gmail.com",                  "Uri#Uri27"),
    ("fabior20@gmail.com",                   "Tutesc#EDLP"),
    ("isa.nunez98@gmail.com",                "Juego con la 10#VAJ"),
    ("martinb22@gmail.com",                  "Patroler#111"),
    ("dani_luna01@gmail.com",                "Josedeoro#RECA"),
    ("sam.pal03@gmail.com",                  "chinoo#1200"),
    ("aracelil20@gmail.com",                 "maidenless#SAPEE"),
    ("enzov21@gmail.com",                    "elSeba11Xx#LAS"),
    ("dayce99@gmail.com",                    "SeeYouSoon#1800"),
    ("hecpinto22@gmail.com",                 "CarpinchoGoD#LAS"),
    ("kiar.a02@gmail.com",                   "TomPlatz#0000"),
    ("serzapata03@gmail.com",                "FRAN MAIRA#3331"),
    ("yescue20@gmail.com",                   "Neurus#LAS"),
    ("alvtafur21@gmail.com",                 "EuLeK#LAS"),
    ("milvera99@gmail.com",                  "Pappers#LAS"),
    ("rodcerna22@gmail.com",                 "KillVMaim#IDFC"),
    ("nat.pezo01@gmail.com",                 "pancito36#4437"),
    ("valeria.ramos22@gmail.com",            "tki44#222"),
    ("luisfernando2003@gmail.com",           "alan2pac#LAS"),
    ("angiecastillo99@gmail.com",            "Aeternum#LAS"),
    ("sebas_palacios01@gmail.com",           "Nomacitax#0069"),
    ("jorgem.reyes20@gmail.com",             "melvin#waos"),
    ("mariapaz.vv@gmail.com",               "Respawn Love#LAS"),
    ("diegochavarria98@gmail.com",           "KrawLee#1997"),
    ("carla.nuñez02@gmail.com",              "frN#0202"),
    ("bryanquispe2005@gmail.com",            "Chrollo Lucifer#HxH1"),
    ("sofiagonzales03@gmail.com",            "Ragnar Lodbrok#VLH"),
    ("andres.vc21@gmail.com",                "imMonster#LAS"),
    ("luciahidalgox@gmail.com",              "Marveliano#UCM"),
    ("pablomedina2002@gmail.com",            "almostdead#lllll"),
    ("natalia.rm01@gmail.com",               "TostadiitaOP#Jesi"),
    ("fernandoag20@gmail.com",               "pudrete616#LAS"),
    ("danielamora.98@gmail.com",             "Rosetta#Lyor"),
    ("kevinhuanca2004@gmail.com",            "ComeToM#LAS"),
    ("camila.soto23@gmail.com",              "VladSuo#CR7"),
    ("joseluisrg99@gmail.com",               "Khada jhin LIBRA#jhin4"),
    ("xiomara.pb03@gmail.com",               "Nagumo Hajime#LAS"),
    ("alexisvillanueva21@gmail.com",         "Labix#Goat"),
    ("karen.mmz02@gmail.com",                "Zheva#LAS"),
    ("rodrigochavez2001@gmail.com",          "Koreback#LAS"),
    ("gaby.lop20@gmail.com",                 "Ðarkîn bøw#GoNxt"),
    ("fabianmontoya98@gmail.com",            "Mikel#SEEEX"),
    ("ale.quiroz22@gmail.com",               "Little Bandido#LAS"),
    ("sebastianfuentes03@gmail.com",         "KNONIMO EL FURIA#LAS"),
    ("isa.delgado21@gmail.com",              "PesoPesado95#LAS"),
    ("juancarlos.hz@gmail.com",              "Sv3n#LAS"),
    ("mireya.vr99@gmail.com",               "ZOYN#LAS"),
    ("andresflores2000@gmail.com",           "Avril#UwU"),
    ("pao.estrada02@gmail.com",              "space cowboy#3194"),
    ("cristian.mb23@gmail.com",              "Pulga De Warwick#00001"),
    ("luciana.tv01@gmail.com",               "Ckotooh#LAS"),
    ("hectorvillalba98@gmail.com",           "Doryani#POET"),
    ("stefy.qq20@gmail.com",                 "Tenshi No Shi#LAS"),
    ("miguelangel.cr@gmail.com",             "BLACK CAT#PIZZA"),
    ("daniela.nv03@gmail.com",               "Yusah#LAS"),
    ("erickmendoza2004@gmail.com",           "RodriDraco#LAS"),
    ("rosaura.ch21@gmail.com",               "Girl is a gun#LAS"),
    ("antoniochavez99@gmail.com",            "Elfaria#1355"),
    ("ana.rojas02@gmail.com",                "Wifelershow#7458"),
    ("willychoque2003@gmail.com",            "TwilightShade#LAS"),
    ("vale.ff20@gmail.com",                  "detructor444#LAS"),
    ("oscarhuaman2001@gmail.com",            "puro ks#002"),
    ("esther.mb22@gmail.com",                "Swain KFC#COMBO"),
    ("cristianzapata03@gmail.com",           "差异顶部#ASR"),
    ("lau.quispe21@gmail.com",               "Ecch#LAS"),
    ("brunomiranda99@gmail.com",             "D4rK Asassin#LAS"),
    ("silvi.mm02@gmail.com",                 "Luis Yeager#LAS"),
    ("elias.torres2004@gmail.com",           "Wagyu#LAS"),
    ("jhanp.cc20@gmail.com",                 "BRG Velois#CEL"),
    ("adrianochoa2002@gmail.com",            "kclak#LAS"),
    ("dani.rm23@gmail.com",                  "Sir Friijooliito#sera"),
    ("pedrohurtado98@gmail.com",             "ivvo18#LAS"),
    ("ceci.vr01@gmail.com",                  "T1 DradKhan#SKT"),
    ("samuelcerda2005@gmail.com",            "ƒiuroxy#loveu"),
    ("ale.pn22@gmail.com",                   "MeDeprimoFacil#uwu"),
    ("gonzalo.mf03@gmail.com",               "hip0frenia#LAS"),
    ("nadia.cf20@gmail.com",                 "未来の音#1999"),
    ("ricardovillena2001@gmail.com",         "Black Ivy#505"),
    ("mafe.ss99@gmail.com",                  "Yuta Okkotsu#5805"),
    ("piero.vt21@gmail.com",                 "EntrandoEnEsa#LAS"),
    ("yuliana.mb02@gmail.com",               "eL Dany DT#LAS"),
    ("joelhuayta2003@gmail.com",             "Lucky 38#Luck7"),
    ("sofia.rc20@gmail.com",                 "Black Insomnia#0589"),
    ("diegomontano98@gmail.com",             "juansethekof#LOS"),
    ("ana.pb03@gmail.com",                   "Белая смерть#АРГ"),
    ("mateo.vv22@gmail.com",                 "C13 Damz#LAS"),
    ("klaudia.rm01@gmail.com",               "c a r ö l i n a#ARS"),
    ("francolazo2004@gmail.com",             "Eifeldor#LAS"),
    ("nat.cv20@gmail.com",                   "Andreik99#999"),
    ("alan.hz99@gmail.com",                  "jodipe#Ahri"),
    ("roxanaquispe2002@gmail.com",           "SQUANCHØ#LAS"),
    ("kev.lm23@gmail.com",                   "AlterMitico#Novus"),
    ("andresbustamante03@gmail.com",         "DAO FUTURE#LAS"),
    ("mary.tf21@gmail.com",                  "yiyawosao#LAS"),
    ("luisquintana2000@gmail.com",           "CSSML NDSML#kahoz"),
    ("caro.mb02@gmail.com",                  "Zaikologic#Zaik"),
    ("eddymendez99@gmail.com",               "qdanm#hiim"),
    ("bel.rv20@gmail.com",                   "OMG Ken#LAS"),
    ("danielcastañeda2003@gmail.com",        "aKaiRe#LAS"),
    ("raquelp.mm@gmail.com",                 "Emahtz#LAS"),
    ("alondra.vv22@gmail.com",               "puckeffideb#LAS"),
    ("franciscocc01@gmail.com",              "Come Around Me#diazk"),
    ("mayte.rb03@gmail.com",                 "NeuraNura#Brem"),
    ("jeanpierre2004@gmail.com",             "xWarRx#LAS"),
    ("dali.cn20@gmail.com",                  "Jaskisceviciuss#LAS"),
    ("victorhugo.mp@gmail.com",              "Don Titi#LAS"),
    ("anita.sz02@gmail.com",                 "SOD Un Oso Wacho#9543"),
    ("ronaldchura2001@gmail.com",            "Ziggsmund Freud#PANDI"),
    ("flor.mv21@gmail.com",                  "Rook Gendarmerie#LAS"),
    ("enriquepm98@gmail.com",                "Tea Lover#gkrmp"),
    ("vane.ql03@gmail.com",                  "chérie lueur#maia"),
    ("marcos.vb22@gmail.com",                "IIIIIIIIIIIII#8413"),
    ("luz.ch20@gmail.com",                   "AlanBritoDl#LAS"),
    ("escuderosantillan@gmail.com",           "jeshuco#777"),
    ("miguelzegarra99@gmail.com",            "zun#TLUCH"),
    ("ara.cc01@gmail.com",                   "Sephiroth#SSSSS"),
    ("humbertofas@gmail.com",                "R Inst#8092"),
]


def main():
    if not KEY_PATH.exists():
        print(f"[ERROR] No se encontró firebase-key.json en {KEY_PATH}")
        sys.exit(1)

    cred = credentials.Certificate(str(KEY_PATH))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    ahora = datetime.now(timezone.utc)

    creados = 0
    existentes = 0
    errores = 0

    print(f"\n{'='*60}")
    print(f"  Creando {len(USUARIOS)} cuentas de participantes")
    print(f"  Contraseña por defecto: {DEFAULT_PASSWORD}")
    print(f"{'='*60}\n")

    for i, (email, riot_id) in enumerate(USUARIOS, 1):
        try:
            # 1. Crear o reutilizar usuario en Firebase Auth
            try:
                record = auth.create_user(
                    email=email,
                    password=DEFAULT_PASSWORD,
                    email_verified=False,
                )
                uid = record.uid
                estado = "CREADO   "
                creados += 1
            except auth.EmailAlreadyExistsError:
                record = auth.get_user_by_email(email)
                uid = record.uid
                estado = "EXISTENTE"
                existentes += 1

            # 2. Crear/actualizar documento en Firestore
            ref = db.collection("usuarios").document(uid)
            ref.set({
                "email": email,
                "riotIdVinculado": riot_id,
                "ultimaActividad": ahora,
            }, merge=True)

            # Asegura que tenga config por defecto
            snap = ref.get()
            if not snap.exists or not snap.to_dict().get("config"):
                ref.set({"config": {
                    "hpdMax": 4.0,
                    "ttsMax": 21.0,
                    "dcjMax": 5,
                    "sleepStart": "23:00",
                    "sleepEnd": "07:00",
                    "sensibilidad": "media",
                    "recordatorios": True,
                    "metas": [],
                }}, merge=True)

            print(f"  [{i:3d}/{len(USUARIOS)}] {estado} | {email:<45} -> {riot_id}")

        except Exception as e:  # noqa: BLE001
            print(f"  [{i:3d}/{len(USUARIOS)}] ERROR     | {email} -> {e}")
            errores += 1

    print(f"\n{'='*60}")
    print(f"  Resultado: {creados} creados · {existentes} ya existían · {errores} errores")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
