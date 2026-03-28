c   ---------------------------------------------------------------------
c
c    Interpolation and coordinate transformation program
c                   for Japanese Geoid Model 2000
c
c                        Ver. 2.4  2010/08/12 
c			      modified COMMENT and PROGRAM NAME
c                        Ver. 2.3  2004/04/05 
c                             append DMSCHK(input_check routine)
c                        Ver. 2.2  2004/03/30 
c                             modified subroutine DMS
c                        Ver. 2.1  2001/03/02 
c                                (changed partly in the interpolation)
c                        Ver. 2.0  2001/02/21 
c                  ---------------------------- Ver.1.* for Geoid Model 96
c                                          Ver. 1.61 1998/02/12  (new format)
c                                          Ver. 1.5  1998/01/23 
c                                          Ver. 1.42 1997/11/07 
c                                          Ver. 1.41 1997/05/16 
c                                          Ver. 1.0  1997/03/28 
c
c       First Geodetic Division, Geodetic Department
c            Geographical Survey Institute
c    
c
c      ( GSIGPS CALCULATION PROGRAM /1994-12-7/(C)M.IWATA & H.TSUJI )
c
c   ---------------------------------------------------------------------
c
c   Input data coordinates must be those in GRS80/ITRF94(97.0)
c   Otherwise, the coordinate conversion should be made beforehand to yield
c   the required coordinates.
c
      PROGRAM GSIGEOME_ASC
        
c USE DFLIB
      CHARACTER NameSTA*18,Infile*50,Outfile*50,Datafile*50,VER*40
      INTEGER NSTA
      REAL*8 LAT,LON
      REAL N
      INTEGER LAT_RET,LON_RET,ALL_FLG
       DATA VER/' GSIGEOME_ASC Ver2.4 2010/08/12 '/
C      DATA VER/' GSIGEOME2 Ver2.2 2004/03/30 YK'/
C      DATA VER/' GSIGEOME2 Ver2.2 2001/02/21 YK'/
      ALL_FLG = 0
      CALL BANNER(6,VER)
      CALL ReadIDX(Infile,Outfile,Datafile)

101   FORMAT(I4,A18,2F15.4)

10    READ (7,101,END=999) NSTA,NameSTA,LAT,LON
      IF ((NameSTA.EQ.'END').OR.(NameSTA.EQ.'end')) GOTO 999
c     ------Process      ------------------------------------
      CALL DMSCHK(LAT,LAT_RET)
      CALL DMSCHK(LON,LON_RET)
      IF ( LAT_RET .EQ. 0 .AND. LON_RET .EQ. 0 ) THEN
        CALL INTERPOLATE(LON,LAT,N)
        CALL PRINT1(LAT,LON,N,NSTA,NameSTA)
      ELSE
        CALL ERR_PRINT(LAT,LON,NSTA,NameSTA)
        ALL_FLG = 1
      END IF
      goto 10

999   IF ( ALL_FLG .EQ. 0 ) THEN
        WRITE(*,*) ' complete! Thank you. '
      ELSE
        WRITE(*,*) ' Error data found.! Check please.'
      END IF
      CLOSE(7)
      CLOSE(8)
      STOP
      END

      SUBROUTINE INTERPOLATE(LON,LAT,N)
C     -------------------------------------------------------
C     「日本のジオイド２０００」モデルの補間プログラム
C     -------------------------------------------------------
      REAL N
      REAL*8 LAT,LON
      real*8 X,Y

      CALL DMS(LON,X)
      CALL DMS(LAT,Y)
      CALL BILINEAR(X,Y,120.D0,20.D0,N)

      RETURN
      END

      SUBROUTINE BILINEAR(XPT,YPT,XMIN,YMIN,Z)
C     ------------------------------------
C        bilinear interpolation
C     ------------------------------------
C      USE DFLIB
      
        REAL*8 XPT,YPT,XMIN,YMIN,DX,DY,X,Y
      REAL Z,dat(1801,1201)
      REAL el2,xx,yy
        INTEGER*4 nla,nlo
      INTEGER IX,IY,JX,JY,IADX,IADY
      common /ght/dat,nla,nlo

      el2 = 1.d-5

      DX=1.5D0/60.D0
      DY=1.D0/60.D0
      IX=INT((XPT-XMIN)/DX)+1
      IY=INT((YPT-YMIN)/DY)+1
      X=(XPT-XMIN)/DX-(IX-1)
      Y=(YPT-YMIN)/DY-(IY-1)
      JX=IX+1
      JY=IY+1
c -------- check if the point is out of the data area
      if((IX.LT.0).OR.(IX.GE.1201).OR.(IY.LT.0).OR.(IY.GE.1801)) THEN
        write(*,*)'error:out of data area'
        Z=999.0
          RETURN
      endif
c -------- check if the point is on the grid point or on a grid line
c        added in Ver.2.1
      yy =DABS(Y)
      xx =DABS(X)
        IADX=99
        IADY=99
      if(yy.lt.el2) THEN
           IADY=0
       else if((1.d0-yy).lt.el2) THEN 
           IADY=1
        end if
        if(xx.lt.el2) THEN
           IADX=0
         else if((1.d0-xx).lt.el2) THEN
           IADX=1
        end if
            
      if(IADY.lt.10) then 
c -----------  the point is on the grid
        if(IADX.lt.10) then 
            Z=dat(IY+IADY,IX+IADX)
          RETURN
          end if
c -----------  the point is on the meridian cell line
        if ((dat(IY+IADY,IX).EQ.999.).OR.(dat(IY+IADY,JX).EQ.999.)) THEN
          write(*,*)'error:non significant data area'
          Z=999.0
        else
            Z=(1.-X)*dat(IY+IADY,IX) + X*dat(IY+IADY,JX)
          end if
        RETURN
        else if(IADX.lt.10) then
c -----------  the point is on the parallel cell line
        if ((dat(IY,IX+IADX).EQ.999.).OR.(dat(JY,IX+IADX).EQ.999.)) THEN
          write(*,*)'error:non significant data area'
          Z=999.0
        else
            Z=(1.-Y)*dat(IY,IX+IADX) + Y*dat(JY,IX+IADX)
        end if
        RETURN
        end if   
c ------------- process for the point which is not on the grid lines
      if (((dat(JY,IX).EQ.999.).OR.(dat(JY,JX).EQ.999.)).OR.
     $    (dat(IY,IX).EQ.999.).OR.(dat(IY,JX).EQ.999.)) THEN
          write(*,*)'error:non significant data area'
          Z=999.0
      else
          Z=(1.-X)*(1.-Y)*dat(IY,IX)+Y*(1.-X)*dat(JY,IX)+X*(1.-Y)*
     $    dat(IY,JX)+dat(JY,JX)*X*Y
      endif
      
      RETURN
      END

      SUBROUTINE DMS(DMS1,DEG)
c     ------------------------------
      real*8 dox,fun,byo,dms1,deg
      DOX= IDINT(DMS1*1.d-4)
      FUN= IDINT(DMOD(DMS1,1.d4)*1.d-2)
      BYO=DMOD(DMS1,1.d2)
c      FUN= INT((DMS1-DOX)*100.0d0+1.e-12)
C      BYO= DMS1 * 10000.0d0 - (DOX * 10000.0d0 + FUN * 100.0d0)
      DEG=DOX+FUN/60.d0+BYO/3600.d0
      RETURN
      END

      SUBROUTINE BANNER(DEV,VER)
C---- PRINT OUT THE BANNER ----------------------------------
C      USE DFLIB
        CHARACTER VER*40
      INTEGER DEV
      WRITE(DEV,*) ('-',I=1,78)
      WRITE(DEV,'(A)') '    ジオイド高内挿計算プログラム'
      WRITE(DEV,'(A)') '    Geoid interpolation Program, GSI'
      WRITE(DEV,'(3X,A40)') VER
      WRITE(DEV,*) ('-',I=1,78)
      RETURN
      END

      SUBROUTINE ReadIDX(Infile,Outfile,Datafile)
C     USE MSFLIB
C     USE DFLIB
C       USE DFPORT
C---- Read the index file  --------------------------------------------
      CHARACTER Infile*50,Outfile*50,Datafile*50
      REAL dat(1801,1201)
      REAL*8 glamn,glomn,dgla,dglo
      INTEGER*4 nla,nlo
      common /ght/dat,nla,nlo

C      if(iargc() .eq. 0) then
       WRITE(*,*) '  '
       WRITE(*,*) '　座標値のファイル名を入力して下さい (例：input.dat)'
       WRITE(*,*) '   format Num(I4),Name(A18),Lat(F15.4),Lon(F15.4)'
       WRITE(*,*) '    Lat=ddmmss.ssss, Lon=dddmmss.ssss'
       READ(*,'(A)') Infile
       WRITE(*,*) '  出力ファイル名を入力して下さい（例：output.dat）'
       READ(*,'(A)') Outfile
       WRITE(*,*) '  ジオイドモデルのファイル名を入力して下さい'
         WRITE(*,*) '    （例：gsigeom5.asc） '
       READ(*,'(A)') Datafile

        write(*,*) 'Infile='//Infile
        write(*,*) 'Outfile='//Outfile
        write(*,*) 'GHTfile='//Datafile

C      else
C        if(iargc() .lt. 3) then
C         WRITE(*,*) 'usage: gsigeome infile outfile datafile coordinate'
C         WRITE(*,*) '  '
C         WRITE(*,*) ' infile    :Input Lat & Lon file name '
C         WRITE(*,*) '   format Num(I4),Name(A18),Lat(F15.4),Lon(F15.4)'
C         WRITE(*,*) '             Lat=ddmmss.ssss, Lon=dddmmss.ssss'
C         WRITE(*,*) ' outfile   :Output file name '
C         WRITE(*,*) '      geoidal height in meter '
C         WRITE(*,*) ' datafile  :Input geoid file name (gsigeome.asc)'
C         WRITE(*,*) '  ' 
C         stop
C        else
C         call getarg(1,Infile)
C         call getarg(2,Outfile)
C         call getarg(3,Datafile)
C        end if
C        end if

C---- Open files  --------------------------------------------
      OPEN (7,FILE=Infile,ERR=97,STATUS='OLD')
      OPEN (8,FILE=Outfile,ERR=99)
      OPEN (9,FILE=Datafile,ERR=98,STATUS='OLD')
C---- Read the geoid file  --------------------------------------------
      WRITE(*,*)' Reading the geoid file. Wait a second...  '

  100 format(2F10.5,2F9.6,2I5,I2)
  101 format(28F9.4)

      read(9,100) glamn,glomn,dgla,dglo,nla,nlo,ikind
      write(*,*)' geoid data file ='//Datafile
      write(*,*)'       number in east-west direction =',nlo
      write(*,*)'       number in north-south direction =',nla

        do i=1,nla
        read(9,101) (dat(i,j),j=1,nlo)
      end do
      close(9)          
      RETURN

97    WRITE(*,*) ' Error in input file name'
      WRITE(*,*) ' 入力パラメータに誤りがあります '
      WRITE(*,*) ' Entered name  ='//Infile
        STOP    
99    WRITE(*,*) ' Erorr in output file name'
      WRITE(*,*) ' 入力パラメータに誤りがあります '
      WRITE(*,*) ' Entered name  ='//Outfile
      WRITE(*,*) '  ' 
      STOP
98    WRITE(*,*) ' Erorr in reading the input geoid data file. '
      WRITE(*,*) ' ジオイドモデル・ファイル名に誤りがあります '
      WRITE(*,*) ' Entered Geoid name ='//Datafile
      STOP
      END

      SUBROUTINE PRINT1(LAT,LON,N,NSTA,NameSTA)
C---- PRINT OUT THE RESULT OF GEOID --------------------
C      USE DFLIB
        CHARACTER NameSTA*18
      REAL*8 LAT,LON
      REAL N
      INTEGER NSTA
      WRITE(8,110) NSTA,NameSTA,LAT,LON,N
C     WRITE(6,110) NSTA,NameSTA,LAT,LON,N
110   FORMAT(I4,A18,3F15.4)
      RETURN
      END

      SUBROUTINE ERR_PRINT(LAT,LON,NSTA,NameSTA)
C---- PRINT OUT THE RESULT OF GEOID --------------------
C      USE DFLIB
        CHARACTER NameSTA*18
      REAL*8 LAT,LON
      INTEGER NSTA
      WRITE(6,110) NSTA,NameSTA,LAT,LON
110   FORMAT("ERROR DATA: ",I4,A18,3F15.4)
      RETURN
      END

      SUBROUTINE DMSCHK(DMS,RET)
C--------------------------------------------------------
      REAL*8 DMS,FUN,BYO
      INTEGER RET
      FUN= IDINT(DMOD(DMS,1.d4)*1.d-2)
      BYO= DMOD(DMS,1.d2)
C     WRITE(*,110) DMS,FUN,BYO
C110  FORMAT(5F15.4)
      RET = 0
      IF ( FUN .GE. 60.0d0 ) THEN
        RET = 1
      END IF
      IF ( BYO .GE. 60.0d0 ) THEN
        RET = 1
      END IF
      END

