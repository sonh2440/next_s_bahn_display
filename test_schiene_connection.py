import schiene
import schieneNew
import datetime
import sys

def main(argv):
        myschiene = schiene.Schiene()
        now = datetime.datetime.now()

        response = myschiene.connections('München-Mittersendling', 'München Hbf', now,
                                           only_direct=True)
        print("Result old:")
        print(response)

        myschienenew = schieneNew.SchieneNew()
        now = datetime.datetime.now()

        response = myschienenew.connections('München-Mittersendling', 'München Hbf', now,
                                           only_direct=True)
        print("Result new:")
        print(response)


if __name__ == '__main__': 
    main(sys.argv[1:])