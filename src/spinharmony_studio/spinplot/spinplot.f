      program spinplot
      
C     This program used to be called distconv.f

      implicit          none
      character*64      spin_file,out_file,write_file
      character*1       tchar
	character*2		itc2
	character*3		prefix
      double precision  pi,histogram(400,400),x,y,z,max,min,theta0,
     +                  dtheta,phi,theta,di2,sumdi2,thetai,phii,rho,c,
     +                  phi0,theta0orig
      integer           ntheta,nphi,npixels,mesh(10000,10000,3),i,j,k,
     +                  itheta,iphi,ix,iy,ttheta,col,count
      logical           file_exists,rotate

      pi=3.1415926535898D0
      
      write(*,*)'Enter name of spin distribution file'
 3000 read(*,*)spin_file
      inquire(file=spin_file,exist=file_exists)
      if(.not.file_exists)then
        write(*,*)'File not found; please re-enter name'
      else
        goto 4000
      endif
      goto 3000
 4000 continue
 
      write(*,*)'Enter name of output file (with extension .ppm)'
      read(*,*)out_file
      open(file=out_file,unit=12)
      open(file=spin_file,unit=9)

      read(9,*)ntheta,nphi
      write(*,*)'ntheta,nphi:',ntheta,nphi
      write(*,*)'Enter number of pixels'
      read(*,*)npixels
      write(*,*)'Enter theta0 in units of dtheta, and phi0 in radians'
      read(*,*)theta0,phi0

      max=0D0
      min=0D0
      
      do i=1,nphi
        read(9,*)(histogram(i,j),j=1,ntheta)
        do j=1,ntheta
          if(histogram(i,j).gt.max)max=histogram(i,j)
          if(histogram(i,j).lt.min)min=histogram(i,j)
        enddo
      enddo
      
      write(*,*)'Max, min values found:',max,min
      write(*,*)'Enter alternate values?'
      read(*,*)tchar
      if((tchar.eq.'y').or.(tchar.eq.'Y'))then
        write(*,*)'Enter new max, min values'
        read(*,*)max,min
      else
        if(-min.gt.max)max=-min
        if(max.gt.-min)min=-max
      endif
      
      write(*,*)'Background colour? (1=white; anything else is black)'
      read(*,*)tchar
      if(tchar.eq.'1')then
        col=255
      else
        col=0
      endif
	
	write(*,*)'Rotate around vertical axis? (T/F; for .gif)'
	read(*,*)rotate

      dtheta=2*pi/dble(ntheta)
	theta0=theta0*dtheta
	if(rotate)theta0=theta0-(dtheta/2D0)
	count=0

 100  continue
 
	count=count+1
	write(*,*)'count',count

      if(rotate)then
	  theta0=theta0+(dtheta/2d0)
	  if(count.eq.((2*ntheta)+1))go to 200
	  if(count.eq.1)close(12)
	  prefix=itc2(count)//'_'
	  open(file=prefix//out_file,unit=12)
	endif

      do i=1,npixels
        do j=1,npixels
          do k=1,3
            mesh(i,j,k)=col
          enddo
        enddo
      enddo
      
      do i=1,npixels
        y=1D0-2D0*((i-0.5)/npixels)
        do j=1,npixels
          x=2D0*((j-0.5)/npixels)-1D0
          rho=dsqrt((x*x)+(y*y))
          if(rho.lt.1d0)c=asin(rho)
          if(rho.le.1D0)then
            phi=(pi/2)-asin(cos(c)*sin(phi0)+(y*sin(c)*cos(phi0)/rho))
            iphi=int(dble(nphi)*(1D0-cos(phi))/2D0)+1
            theta=theta0+atan2(x*sin(c),((rho*cos(phi0)*cos(c))-
     +                        (y*sin(phi0)*sin(c))))
            itheta=int(dble(ntheta)*(theta/(2*pi)))+1
            if(itheta.gt.ntheta)itheta=itheta-ntheta
            if(itheta.lt.1)itheta=itheta+ntheta
            if((theta.eq.((itheta-0.5)*dtheta)).and.
     +         (phi.eq.((iphi-0.5)/nphi)))then
              z=histogram(iphi,itheta)
            elseif(iphi.eq.1)then
              sumdi2=0D0
              z=0D0
              do ix=-1,1,1
                do iy=0,1,1
                  thetai=dtheta*(itheta+ix-0.5)
                  if(thetai-theta.gt.2*dtheta)thetai=thetai-2*pi
                  if(thetai-theta.lt.-2*dtheta)thetai=thetai+2*pi
                  phii=acos(1-2D0*(iphi+iy-0.5)/nphi)
                  di2=(theta-thetai)**2
                  di2=di2+((phi-phii)**2)
                  di2=1D0/(di2)**1.8
                  sumdi2=sumdi2+di2
                  ttheta=itheta+ix
                  if(ttheta.gt.ntheta)ttheta=ttheta-ntheta
                  if(ttheta.lt.1)ttheta=ttheta+ntheta
                  z=z+histogram(iphi+iy,ttheta)*di2
                enddo
              enddo
              z=z/sumdi2
            elseif(iphi.eq.nphi)then
              sumdi2=0D0
              z=0D0
              do ix=-1,1,1
                do iy=-1,0,1
                  thetai=dtheta*(itheta+ix-0.5)
                  if(thetai-theta.gt.2*dtheta)thetai=thetai-2*pi
                  if(thetai-theta.lt.-2*dtheta)thetai=thetai+2*pi
                  phii=acos(1-2D0*(iphi+iy-0.5)/nphi)
                  di2=(theta-thetai)**2
                  di2=di2+((phi-phii)**2)
                  di2=1D0/(di2)**1.8
                  sumdi2=sumdi2+di2
                  ttheta=itheta+ix
                  if(ttheta.gt.ntheta)ttheta=ttheta-ntheta
                  if(ttheta.lt.1)ttheta=ttheta+ntheta
                  z=z+histogram(iphi+iy,ttheta)*di2
                enddo
              enddo
              z=z/sumdi2
            else
              sumdi2=0D0
              z=0D0
              do ix=-1,1,1
                do iy=-1,1,1
                  thetai=dtheta*(itheta+ix-0.5)
                  if(thetai-theta.gt.2*dtheta)thetai=thetai-2*pi
                  if(thetai-theta.lt.-2*dtheta)thetai=thetai+2*pi
                  phii=acos(1-2D0*(iphi+iy-0.5)/nphi)
                  di2=(theta-thetai)**2
                  di2=di2+((phi-phii)**2)
                  di2=1D0/(di2)**1.8
                  sumdi2=sumdi2+di2
                  ttheta=itheta+ix
                  if(ttheta.gt.ntheta)ttheta=ttheta-ntheta
                  if(ttheta.lt.1)ttheta=ttheta+ntheta
                  z=z+histogram(iphi+iy,ttheta)*di2
                enddo
              enddo
              z=z/sumdi2
            endif
            
            if(z.gt.max)z=max
            if(z.lt.min)z=min
            
            if(z.lt.0D0)then
              mesh(i,j,1)=255-int(255D0*(z/min))
              mesh(i,j,2)=0
              mesh(i,j,3)=0
C              mesh(i,j,1)=0
C              mesh(i,j,2)=150-int(150D0*(z/min))
C              mesh(i,j,3)=0
C              mesh(i,j,1)=int(255D0*(z/min))
C              mesh(i,j,2)=255-int(255D0*(z/min))
C              mesh(i,j,3)=0
C            else
C              mesh(i,j,1)=0
C              mesh(i,j,2)=255-int(255D0*(z/max))
C              mesh(i,j,3)=int(255D0*(z/max))
            elseif(z.lt.(0.66667*max))then
              mesh(i,j,1)=255
              mesh(i,j,2)=int(255D0*(z/(0.66667*max)))
              mesh(i,j,3)=0
C              mesh(i,j,1)=int(255D0*(z/(0.66667*max)))
C              mesh(i,j,2)=150
C              mesh(i,j,3)=int(150D0*(z/(0.66667*max)))
            else
              mesh(i,j,1)=255
              mesh(i,j,2)=255
              mesh(i,j,3)=int(255D0*((z-0.66667*max)/(0.33333*max)))
C              mesh(i,j,1)=255
C              mesh(i,j,2)=150+int(105*((z-0.66667*max)/(0.33333*max)))
C              mesh(i,j,3)=150+int(105*((z-0.66667*max)/(0.33333*max)))
            endif
          endif
        enddo
      enddo

      write(12,'(A2,1X,2(I5,1X),A3)')'P3',npixels,npixels,'255'
      do i=1,npixels
        write(12,'(4000(3(I3,1X),2X))')
     +       (mesh(i,j,1),mesh(i,j,2),mesh(i,j,3),j=1,npixels)
      enddo
      write(12,'(/)')
      
      close(12)
	
	if(rotate) go to 100
	
 200  continue
      
      end



	function itc2(count)
	
	implicit none
	
	integer count,i1,i2
	character*2	itc2
	character*1	c1,c2
	
	count=mod(count,100)
	i1=count/10
	i2=count-(i1*10)
	if(i1.eq.0)c1='0'
	if(i1.eq.1)c1='1'
	if(i1.eq.2)c1='2'
	if(i1.eq.3)c1='3'
	if(i1.eq.4)c1='4'
	if(i1.eq.5)c1='5'
	if(i1.eq.6)c1='6'
	if(i1.eq.7)c1='7'
	if(i1.eq.8)c1='8'
	if(i1.eq.9)c1='9'
	if(i2.eq.0)c2='0'
	if(i2.eq.1)c2='1'
	if(i2.eq.2)c2='2'
	if(i2.eq.3)c2='3'
	if(i2.eq.4)c2='4'
	if(i2.eq.5)c2='5'
	if(i2.eq.6)c2='6'
	if(i2.eq.7)c2='7'
	if(i2.eq.8)c2='8'
	if(i2.eq.9)c2='9'
	itc2=c1//c2
	
	end
